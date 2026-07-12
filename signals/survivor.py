"""생존자 지수(M2) — 그 자리의 평균 생존기간 대비 얼마나 오래 버티는가.

자리회전(같은 주소에서 폐업 이력)이 있는데도 오래 버틴 집은 입지가 아니라 실력으로
버티는 집이라는 가설의 신호화. 자리별 평균 생존기간은 그 주소에서 과거 폐업한
업소들의 (폐업일자-인허가일자) 평균이며, 이력이 없는 자리는 지역 전체 평균으로
대체한다. LOCALDATA(행안부 인허가) 단독으로 계산 가능.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.outlook import address_key
from signals.registry import register_signal

# 자리 평균 생존기간의 이 배수부터 만점(1.0). 1.0 = "그 자리 평균만큼 버텼는가"에서 포화 —
# 그 이상 나이를 먹어도 점수가 계속 오르지 않는다. 오래된 노포일수록 공급사 관계가 굳어
# 있어 영업 가치가 비례 상승하지 않는다는 피드백 반영 (2026-07-06): 생존 검증은 등급이지
# 나이 순위가 아니다.
MAX_RATIO = 1.0


@register_signal
class Survivor:
    id = "survivor"
    label = "생존자 지수"
    badge_icon = "🌳"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]].copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        closed = df[~df[schema.IS_OPEN]].dropna(subset=[schema.CLOSED_AT]).copy()
        if len(closed) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)  # 폐업 이력 자체가 없으면 기준을 못 세운다
        closed["_주소키"] = address_key(closed)
        closed["_생존기간"] = (closed[schema.CLOSED_AT] - closed[schema.LICENSED_AT]).dt.days / 365.25
        site_stats = closed.groupby("_주소키")["_생존기간"].agg(["mean", "size"])
        area_avg = float(site_stats["mean"].mean())
        # 자리평균 축소추정: 폐업 1건짜리 자리의 0.2년 같은 소표본 평균을 그대로 쓰면
        # "그 자리 평균 생존 0.2년의 10배" 같은 배지가 나온다 — 표본 수(n)만큼만 자리
        # 관측을 믿고 나머지는 지역 평균으로 채운다 (n이 클수록 자리 관측에 수렴).
        site_avg = (site_stats["size"] * site_stats["mean"] + area_avg) / (site_stats["size"] + 1)
        site_turnover = site_stats["size"]

        open_df["_주소키"] = address_key(open_df)
        open_df["_업력"] = (ctx.now - open_df[schema.LICENSED_AT]).dt.days / 365.25
        open_df["_자리평균"] = open_df["_주소키"].map(site_avg).fillna(area_avg)
        open_df["_자리회전수"] = open_df["_주소키"].map(site_turnover).fillna(0).astype(int)

        rows = []
        for _, row in open_df.iterrows():
            if row["_자리평균"] <= 0:
                continue
            ratio = row["_업력"] / row["_자리평균"]
            value = max(0.0, min(1.0, ratio / MAX_RATIO))
            turnover_txt = f"자리회전 {row['_자리회전수']}회 주소에서 " if row["_자리회전수"] > 0 else ""
            # 배지는 자리 평균 이상 버틴 경우에만 — "0.0년째 영업 중"은 사실이지만 신호가 아니다
            badge = (
                f"{self.badge_icon} {turnover_txt}{row['_업력']:.1f}년째 영업 중 "
                f"(그 자리 평균 생존 {row['_자리평균']:.1f}년의 {ratio:.1f}배)"
                if ratio >= 1.0
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(value, 4),
                    RAW: round(row["_업력"], 2),
                    BADGE: badge,
                    DETAIL: (
                        f"인허가일자 {row[schema.LICENSED_AT]:%Y-%m-%d} 기준, 지역 평균 생존기간 {area_avg:.1f}년. "
                        "자리 평균은 폐업 표본 수만큼 지역 평균과 혼합(축소추정)"
                    ),
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

"""알려진 스타 신호 — 현재 블로그 게재 속도(월 환산)의 구역 내 백분위.

리뷰 모멘텀·목적지 지수와 축이 다르다: **업력으로 나누지 않는다** — "지금 언급량이
큰 계정"의 규모를 그대로 본다. 누적 절대량은 쓰지 않는다(업력·과거 마케팅의 함수라
식은 스타가 남는다) — 최근 창의 속도가 '지금도 스타인가'를 판정한다.

증분(최근 90일 vs 직전 90일)은 판정 기준이 아니라 배지의 변곡 정보다. 급증·급감
모두 관측 사실로만 표기한다 (해석·추천 문구 금지 원칙).

API 100건 캡 대응 (datasources/naver.py는 최신순 최대 100건):
- 최신 100건이 최근 180일 창을 다 덮으면(=페이로드가 창보다 김) 창 건수를 그대로 센다.
- 100건이 창 안에 몰려 있으면(=진짜 스타, 창 건수가 잘림) 100건의 날짜 범위로 속도를
  잰다 — 하한이지만 비례는 유지된다. 이때 직전 창은 과소집계라 **증감 배지는 생략**
  (가짜 급증 방지).

blog_post_dates는 리뷰 모멘텀과 같은 쿼리·파일 캐시를 쓰므로 추가 쿼터 소비가 없다.
"""

import pandas as pd

from core import schema
from datasources import naver
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.registry import register_signal

RATE_WINDOW_DAYS = 180
TREND_WINDOW_DAYS = 90
PAYLOAD_CAP = 100      # Naver API display 상한 — 이 개수면 잘렸다고 본다
STAR_TOP_SHARE = 0.2   # 게재 속도 상위 20%만 스타 배지
MIN_PRIOR_POSTS = 5    # 증감 % 분모 최소값 — 소표본이면 증감 생략


def _rate_and_trend(dates: list[pd.Timestamp], now: pd.Timestamp) -> tuple[float, float | None, str]:
    """(게재 속도 건/일, 증감비 또는 None, 계산 근거 문구)."""
    if not dates:
        return 0.0, None, "블로그 관측 없음"
    window_start = now - pd.Timedelta(days=RATE_WINDOW_DAYS)
    oldest = dates[-1]
    if len(dates) >= PAYLOAD_CAP and oldest > window_start:
        # 캡에 잘린 진짜 스타 — 100건의 날짜 범위로 속도를 재고 증감은 생략
        span_days = max((now - oldest).days, 1)
        return len(dates) / span_days, None, (
            f"최신 {len(dates)}건이 {span_days}일에 몰림(API 캡) — 날짜 범위 기준 속도, 증감 생략"
        )
    recent_window = sum(d >= window_start for d in dates)
    rate = recent_window / RATE_WINDOW_DAYS
    mid = now - pd.Timedelta(days=TREND_WINDOW_DAYS)
    recent_half = sum(d >= mid for d in dates)
    prior_half = recent_window - recent_half
    trend = (recent_half - prior_half) / prior_half if prior_half >= MIN_PRIOR_POSTS else None
    return rate, trend, f"최근 {RATE_WINDOW_DAYS}일 창 {recent_window}건 기준"


@register_signal
class StarLevel:
    id = "star_level"
    label = "알려진 스타"
    badge_icon = "⭐"
    requires = frozenset({"moi", "naver"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]]
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        computed = []
        for _, row in open_df.iterrows():
            token = naver.address_token(row[schema.ADDR_ROAD], row[schema.ADDR_JIBUN])
            dates = naver.blog_post_dates(row[schema.NAME], token)
            rate, trend, basis = _rate_and_trend(dates, ctx.now)
            computed.append(
                {EST_ID: row[schema.SRC_ID], "_속도": rate, "_증감": trend,
                 DETAIL: f"'{row[schema.NAME]} {token}' 검색, {basis}"}
            )

        frame = pd.DataFrame(computed)
        rates = frame["_속도"]
        pctile = rates.rank(pct=True)
        badge_cut = rates.quantile(1 - STAR_TOP_SHARE)

        rows = []
        for i, rec in frame.iterrows():
            rate = rec["_속도"]
            badge = None
            if rate > 0 and rate >= badge_cut:
                monthly = rate * 30
                top_pct = max(1, round((1 - pctile.iloc[i]) * 100))
                badge = f"{self.badge_icon} 블로그 월 {monthly:.1f}건 페이스 (수집 반경 내 상위 {top_pct}%)"
                # None은 DataFrame을 거치며 float 컬럼에서 NaN이 된다 — is not None으로는
                # 못 거른다 (weighted_sum의 배지 NaN 함정과 동일, 실데이터에서 "+nan%" 재현됨)
                if pd.notna(rec["_증감"]):
                    badge += f" · 최근 {TREND_WINDOW_DAYS}일이 직전 {TREND_WINDOW_DAYS}일 대비 {rec['_증감']:+.0%}"
            rows.append(
                {
                    EST_ID: rec[EST_ID],
                    VALUE: round(float(pctile.iloc[i]), 4),
                    RAW: round(rate * 30, 2),  # 건/월
                    BADGE: badge,
                    DETAIL: rec[DETAIL],
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

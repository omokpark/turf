"""야간 상권 지수(M7 v1) — 밤에 사람이 있고, 술 마시는 동선 위인가.

v1 구성(계획서): 주류친화 업태 비중(무료, 업소별 변별) × 심야 생활인구(서울 열린데이터
광장, 구역 맥락). 지하철 심야 승하차는 역 좌표 매핑이 필요해 v1.1로 미룸.

- 업소별 축: 반경 300m 이웃 중 주류친화(affinity≥1) 업소 비중 → 구역 내 백분위.
- 구역 축: 분석 중심의 행정동 심야(23~04시) 생활인구 / 전일 평균 비율(0~1로 클립).
  도보 반경(≤400m)은 행정동 1~2개 안이라 중심 1회 조회로 근사한다 (v1 단순화).
- 값 = 업소별 백분위 × 구역 심야 비율. 서울 밖(행정동 매핑 실패)이면 빈 결과로 강등.

배지는 주류친화 비중 상위 20% 업소에만 — 사실만 적는다 (비중·심야 비율·기준일).
"""

import numpy as np
import pandas as pd

from core import area as area_mod
from core import schema
from datasources import seoul
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.outlook import liquor_affinity
from signals.registry import register_signal

NEIGHBOR_RADIUS_M = 300
BADGE_TOP_SHARE = 0.2  # 상위 20%만 배지
MIN_NEIGHBORS = 5  # 이웃이 너무 적으면 비중이 불안정 — 계산은 하되 배지 억제


@register_signal
class NightIndex:
    id = "night_index"
    label = "야간 상권 지수"
    badge_icon = "🌙"
    requires = frozenset({"moi", "seoul"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]].dropna(subset=[schema.LAT, schema.LON]).copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        dong = seoul.dong_of(ctx.area.cx, ctx.area.cy)
        night = seoul.night_population_share(dong[0]) if dong else None
        if night is None or night.get("비율") is None:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)  # 서울 밖 등 — 우아한 강등
        night_factor = float(np.clip(night["비율"], 0.0, 1.0))

        lat = open_df[schema.LAT].to_numpy()
        lon = open_df[schema.LON].to_numpy()
        # affinity >= 2 (호프·주점급)만 센다 — 한식 등 일반음식은 affinity 1(반주 가능)이라
        # >=1 기준으로는 거의 전부가 주류친화가 되어 변별력이 사라진다.
        affinity = np.array(
            [
                liquor_affinity(row[schema.CAT_S], row[schema.NAME]) >= 2
                for _, row in open_df.iterrows()
            ]
        )
        mdl = area_mod.meters_per_deg_lon(float(np.median(lat)))
        shares = np.zeros(len(open_df))
        neighbor_counts = np.zeros(len(open_df), dtype=int)
        for i in range(len(open_df)):
            dx = (lon - lon[i]) * mdl
            dy = (lat - lat[i]) * area_mod.METERS_PER_DEG_LAT
            near = (dx * dx + dy * dy) <= NEIGHBOR_RADIUS_M**2
            neighbor_counts[i] = int(near.sum())
            shares[i] = float(affinity[near].mean()) if near.any() else 0.0

        share_series = pd.Series(shares, index=open_df.index)
        pctile = share_series.rank(pct=True)
        badge_cut = share_series.quantile(1 - BADGE_TOP_SHARE)

        rows = []
        for i, (idx, row) in enumerate(open_df.iterrows()):
            share = shares[i]
            value = round(float(pctile.loc[idx]) * night_factor, 4)
            badge = None
            if share >= badge_cut and neighbor_counts[i] >= MIN_NEIGHBORS:
                badge = (
                    f"{self.badge_icon} 주변 300m 주류친화 비중 {share:.0%} · "
                    f"심야(23~04시) 생활인구 = 전일 평균의 {night['비율']:.0%} ({dong[1]})"
                )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: value,
                    RAW: round(share, 4),
                    BADGE: badge,
                    DETAIL: (
                        f"심야 비율 기준일 {night['기준일']} (서울 생활인구, 행정동 {dong[1]}), "
                        f"주류친화 판정은 업태·상호 키워드 (signals/outlook.liquor_affinity)"
                    ),
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

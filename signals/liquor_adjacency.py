"""주류 인접성 지수(M5) — 반경 300m 내 주류친화 업소 밀도.

단독 랭킹이 아니라 다른 신호의 부스터로 쓰기 위한 신호(scorers.weighted_sum의 낮은
기본 가중치 참고). "술 마시러 오는 동선" 위에 있는 업소인지를, 그 업소를 중심으로 한
반경 내 주류친화 업태(단란·유흥·호프 등, signals.outlook.is_liquor_friendly 기준)
개수로 근사한다.
"""

import numpy as np
import pandas as pd

from core import area as area_mod
from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.outlook import is_liquor_friendly
from signals.registry import register_signal

ADJACENCY_RADIUS_M = 300
SATURATION_COUNT = 10  # 이 개수부터 만점 — 그 이상은 밀집도 차이가 체감상 크지 않다고 봄


@register_signal
class LiquorAdjacency:
    id = "liquor_adjacency"
    label = "주류 인접성 지수"
    badge_icon = "🍻"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN] & df[schema.LAT].notna() & df[schema.LON].notna()].copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        liquor = open_df[is_liquor_friendly(open_df[schema.CAT_S], open_df[schema.NAME])]
        if len(liquor) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        lat = open_df[schema.LAT].to_numpy()
        lon = open_df[schema.LON].to_numpy()
        liquor_lat = liquor[schema.LAT].to_numpy()
        liquor_lon = liquor[schema.LON].to_numpy()
        liquor_ids = set(liquor[schema.SRC_ID])
        mdl = area_mod.meters_per_deg_lon(float(np.median(lat)))

        rows = []
        for i, (_, row) in enumerate(open_df.iterrows()):
            dx = (liquor_lon - lon[i]) * mdl
            dy = (liquor_lat - lat[i]) * area_mod.METERS_PER_DEG_LAT
            count = int(((dx * dx + dy * dy) <= ADJACENCY_RADIUS_M**2).sum())
            if row[schema.SRC_ID] in liquor_ids:
                count = max(0, count - 1)  # 자기 자신 제외
            value = min(1.0, count / SATURATION_COUNT)
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(value, 4),
                    RAW: count,
                    BADGE: f"{self.badge_icon} 반경 {ADJACENCY_RADIUS_M}m 내 주류친화 업소 {count}곳" if count > 0 else None,
                    DETAIL: f"단란·유흥·호프 등 업태 또는 상호명 키워드 기준 (반경 {ADJACENCY_RADIUS_M}m)",
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

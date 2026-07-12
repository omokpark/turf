"""업종 전환 벡터(M6) — 이 자리의 업태 교체가 주류친화 방향인가.

카페 자리에 호프가 들어온 골목 = 주류 수요가 자라는 골목. 자리(주소키) 단위로
직전 폐업 업소의 업태와 현재 업소의 업태를 비교해 주류친화도(0~3)의 변화를 잰다.
카페(0)→호프(2) 전환이면 Δ+2 — 이 업소는 "밤 수요를 보고 들어온 집"일 가능성.

한계(투명 공개): 같은 주소 문자열 = 같은 점포가 아닐 수 있다(한 건물 여러 호수 중
표기가 겹치는 경우). 주소키는 호실 수준을 유지하되 법정동 주석·공백 차이만 정규화한다.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.outlook import address_key, liquor_affinity
from signals.registry import register_signal

MAX_DELTA = 3  # 주류친화도 척도 폭 (0~3) — 값 정규화 분모


@register_signal
class ConversionVector:
    id = "conversion_vector"
    label = "업종 전환 벡터"
    badge_icon = "🔁"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]].copy()
        closed = df[~df[schema.IS_OPEN]].dropna(subset=[schema.CLOSED_AT]).copy()
        if len(open_df) == 0 or len(closed) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        open_df["_주소키"] = address_key(open_df)
        closed["_주소키"] = address_key(closed)
        open_df = open_df[open_df["_주소키"].str.len() > 0]
        closed = closed[closed["_주소키"].str.len() > 0]

        # 각 영업중 업소의 '직전 입주자': 같은 주소에서 이 업소 인허가 전에 폐업한 가장 최근 업소
        predecessors = (
            pd.merge_asof(
                open_df.sort_values(schema.LICENSED_AT)[
                    ["_주소키", schema.SRC_ID, schema.NAME, schema.CAT_S, schema.CAT_L, schema.LICENSED_AT]
                ],
                closed.sort_values(schema.CLOSED_AT)[
                    ["_주소키", schema.NAME, schema.CAT_S, schema.CAT_L, schema.CLOSED_AT]
                ].rename(
                    columns={schema.NAME: "_전상호", schema.CAT_S: "_전업태", schema.CAT_L: "_전업종"}
                ),
                left_on=schema.LICENSED_AT,
                right_on=schema.CLOSED_AT,
                by="_주소키",
                direction="backward",
                allow_exact_matches=False,
            )
            .dropna(subset=["_전업태"])
        )
        if len(predecessors) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        rows = []
        for _, row in predecessors.iterrows():
            prev_aff = liquor_affinity(row["_전업태"], row["_전상호"], row["_전업종"])
            cur_aff = liquor_affinity(row[schema.CAT_S], row[schema.NAME], row[schema.CAT_L])
            delta = cur_aff - prev_aff
            value = max(0.0, delta / MAX_DELTA)  # 주류친화 방향 전환만 점수화, 반대는 0
            badge = (
                f"{self.badge_icon} 이 자리 {row['_전업태']}→{row[schema.CAT_S]} 전환 (주류친화 {prev_aff}→{cur_aff})"
                if delta > 0
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(value, 4),
                    RAW: delta,
                    BADGE: badge,
                    DETAIL: (
                        f"직전 입주자 '{row['_전상호']}' ({row['_전업태']}, {row[schema.CLOSED_AT]:%Y-%m-%d} 폐업) "
                        f"→ 현재 {row[schema.CAT_S]}"
                    ),
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

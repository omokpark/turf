"""상권 성장 모멘텀(M3) — 이 업소가 선 골목(격자)의 개업 가속도.

인허가는 소문보다 3~6개월 빠른 선행지표다: 개업이 가속 중인 격자의 업소는
상권이 커지는 판 위에 있다. 신호값은 업소 자체가 아니라 업소가 속한 500m 격자의
값 — 같은 골목 업소들은 같은 모멘텀을 공유한다 (부스터 성격, 가중 0.5).

격자 통계는 반경 필터 전의 기준 명부(ctx.reference, 수집 자치단체 전체)로 계산해
경계 절단을 피하고, 값(0~1)은 유효 격자들 사이의 percentile로 상대화한다.
분모는 활성업소 수(하한 MIN_ACTIVE) — 원래 큰 상권의 절대량 착시를 제거
(계획서의 SGIS 사업체 수 정규화는 SGIS 키 확보 후 교체 여지).
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.outlook import grid_cell_ids
from signals.registry import register_signal

MIN_ACTIVE = 5  # 소표본 격자의 모멘텀 폭주 방지 (계획서 "분모 하한 5")
BADGE_PERCENTILE = 0.8  # 이 백분위 이상 격자만 배지 — 상위 골목만 신호로 승격


def _cell_stats(reference: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """격자별 (최근 12M 개업, 직전 12M 개업, 활성업소, 모멘텀, percentile)."""
    coords = reference.dropna(subset=[schema.LAT, schema.LON]).copy()
    if len(coords) == 0:
        return pd.DataFrame()
    coords["_셀"] = grid_cell_ids(coords)
    recent = coords[schema.LICENSED_AT].between(now - pd.DateOffset(months=12), now)
    prev = coords[schema.LICENSED_AT].between(now - pd.DateOffset(months=24), now - pd.DateOffset(months=12))
    all_cells = coords["_셀"].unique()
    stats = pd.DataFrame(index=pd.Index(all_cells, name="_셀"))
    stats["최근개업"] = coords[recent].groupby("_셀").size().reindex(stats.index, fill_value=0)
    stats["직전개업"] = coords[prev].groupby("_셀").size().reindex(stats.index, fill_value=0)
    stats["활성"] = coords[coords[schema.IS_OPEN]].groupby("_셀").size().reindex(stats.index, fill_value=0)
    valid = stats[stats["활성"] >= MIN_ACTIVE].copy()
    if len(valid) == 0:
        return pd.DataFrame()
    valid["모멘텀"] = (valid["최근개업"] - valid["직전개업"]) / valid["활성"].clip(lower=MIN_ACTIVE)
    valid["백분위"] = valid["모멘텀"].rank(pct=True)
    return valid


@register_signal
class GrowthMomentum:
    id = "growth_momentum"
    label = "상권 성장 모멘텀"
    badge_icon = "📈"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        reference = ctx.reference if ctx.reference is not None else ctx.establishments
        cells = _cell_stats(reference, ctx.now)
        if len(cells) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        open_df = ctx.establishments[ctx.establishments[schema.IS_OPEN]].dropna(
            subset=[schema.LAT, schema.LON]
        ).copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)
        open_df["_셀"] = grid_cell_ids(open_df)

        rows = []
        for _, row in open_df.iterrows():
            cell = cells.loc[cells.index == row["_셀"]]
            if len(cell) == 0:  # 활성 5곳 미만 격자 — 표본 부족으로 중립
                rows.append(
                    {EST_ID: row[schema.SRC_ID], VALUE: 0.0, RAW: None, BADGE: None,
                     DETAIL: "격자 활성업소 5곳 미만 — 모멘텀 표본 부족"}
                )
                continue
            c = cell.iloc[0]
            pct = float(c["백분위"])
            badge = (
                f"{self.badge_icon} 이 골목 최근 12개월 개업 {int(c['최근개업'])}곳"
                f"(직전 12개월 {int(c['직전개업'])}곳) — 수집 구역 격자 상위 {(1 - pct) * 100:.0f}%"
                if pct >= BADGE_PERCENTILE and c["최근개업"] > c["직전개업"]
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(pct, 4),
                    RAW: round(float(c["모멘텀"]), 4),
                    BADGE: badge,
                    DETAIL: f"500m 격자 기준 개업 {int(c['최근개업'])}→활성 {int(c['활성'])}곳, 모멘텀 {c['모멘텀']:+.3f}",
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

"""주류친화 전환율 — 신규 개업 중 주류친화 업태 비중의 변화

카페 골목이 밤 골목으로 변하는 중인가. 주류 영업 관점에서 가장 직결되는 구성 변화.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import grid_percentile, is_liquor_friendly
from signals.registry import register_indicator


def _liquor_share(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float | None, int]:
    """(기간 내 신규 개업 중 주류친화 비중 0~1, 개업 수)."""
    openings = df[df[schema.LICENSED_AT].between(start, end)]
    if len(openings) == 0:
        return None, 0
    share = is_liquor_friendly(openings[schema.CAT_S], openings[schema.NAME]).mean()
    return float(share), len(openings)


@register_indicator
class LiquorShift:
    id = "liquor_shift"
    label = "주류친화 전환율"
    requires = frozenset({"moi"})

    @staticmethod
    def fmt(value: float) -> str:
        return f"{value * 100:.0f}%"

    def compute(self, ctx: AreaContext) -> IndicatorResult:
        df = ctx.establishments
        now = ctx.now
        current, n_cur = _liquor_share(df, now - pd.DateOffset(months=24), now)
        previous, n_prev = _liquor_share(df, now - pd.DateOffset(months=48), now - pd.DateOffset(months=24))

        rows = []
        for y in range(now.year - 6, now.year + 1):
            share, n = _liquor_share(df, pd.Timestamp(year=y, month=1, day=1), pd.Timestamp(year=y, month=12, day=31))
            if share is not None:
                rows.append({"연도": y, "주류친화비중": round(share * 100, 1), "개업수": n})
        series = pd.DataFrame(rows)

        percentile = None
        if ctx.reference is not None and current is not None:
            percentile = grid_percentile(
                ctx.reference,
                lambda cell: _liquor_share(cell, now - pd.DateOffset(months=24), now)[0],
                current,
            )
        prev_txt = f"{previous * 100:.0f}%" if previous is not None else "표본 없음"
        return IndicatorResult(
            current=current if current is not None else float("nan"),
            previous=previous,
            series=series,
            percentile=percentile,
            fact=(
                f"최근 2년 신규 개업 {n_cur}곳 중 주류친화 업태 {current * 100:.0f}% (직전 2년 {prev_txt}·{n_prev}곳)"
                if current is not None
                else "최근 2년 신규 개업이 없습니다"
            ),
        )

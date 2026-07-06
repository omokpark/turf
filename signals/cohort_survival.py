"""신규 생존율 추이 — 개업 코호트별 1년 생존율

개업 수가 늘어도 다 금방 죽으면 허수다. 이 지표가 상권의 체력(질적 개선)을 본다.
완결 코호트만 사용: 연도 y 코호트의 1년 생존 여부는 y+1년 말까지 관측해야 확정되므로,
최신 완결 코호트는 (올해-2)년이다.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import grid_percentile
from signals.registry import register_indicator

SURVIVAL_DAYS = 365


def _cohort_rate(df: pd.DataFrame, year: int) -> tuple[float | None, int]:
    """(1년 생존율 0~1, 코호트 크기). 코호트가 없으면 (None, 0)."""
    cohort = df[df[schema.LICENSED_AT].dt.year == year]
    if len(cohort) == 0:
        return None, 0
    lifespan = (cohort[schema.CLOSED_AT] - cohort[schema.LICENSED_AT]).dt.days
    died_early = cohort[schema.CLOSED_AT].notna() & (lifespan <= SURVIVAL_DAYS)
    return float(1 - died_early.mean()), len(cohort)


@register_indicator
class CohortSurvival:
    id = "cohort_survival"
    label = "신규 생존율"
    requires = frozenset({"moi"})

    @staticmethod
    def fmt(value: float) -> str:
        return f"{value * 100:.0f}%"

    def compute(self, ctx: AreaContext) -> IndicatorResult:
        df = ctx.establishments
        latest_complete = ctx.now.year - 2
        current, n_cur = _cohort_rate(df, latest_complete)
        previous, n_prev = _cohort_rate(df, latest_complete - 1)

        rows = []
        for y in range(latest_complete - 4, latest_complete + 1):
            rate, n = _cohort_rate(df, y)
            if rate is not None:
                rows.append({"코호트연도": y, "생존율": round(rate * 100, 1), "코호트크기": n})
        series = pd.DataFrame(rows)

        percentile = None
        if ctx.reference is not None and current is not None:
            percentile = grid_percentile(
                ctx.reference, lambda cell: _cohort_rate(cell, latest_complete)[0], current
            )
        return IndicatorResult(
            current=current if current is not None else float("nan"),
            previous=previous,
            series=series,
            percentile=percentile,
            fact=(
                f"{latest_complete}년 개업 {n_cur}곳의 1년 생존율 {current * 100:.0f}% "
                f"(전년 코호트 {previous * 100:.0f}%·{n_prev}곳)"
                if current is not None and previous is not None
                else f"{latest_complete}년 개업 코호트 표본이 부족합니다 ({n_cur}곳)"
            ),
        )

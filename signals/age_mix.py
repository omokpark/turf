"""업력 구성 — 영업중 업소의 신생(2년 미만) vs 장수(7년 이상) 비중

젊은 상권(변동 크고 신규 계약 기회 많음)인지 성숙 상권(안정적이지만 거래선 고착)인지
프로파일을 보여준다. current = 신생 비중.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import grid_percentile
from signals.registry import register_indicator

YOUNG_YEARS = 2
MATURE_YEARS = 7
_BUCKETS = [(0, 2, "2년 미만"), (2, 7, "2~7년"), (7, 15, "7~15년"), (15, 200, "15년 이상")]


def _shares(df: pd.DataFrame, now: pd.Timestamp) -> tuple[float | None, float | None, int, pd.Series | None]:
    """(신생 비중, 장수 비중, 영업중 수, 업력년 시리즈)."""
    alive = df[df[schema.IS_OPEN]]
    if len(alive) == 0:
        return None, None, 0, None
    age_years = (now - alive[schema.LICENSED_AT]).dt.days / 365.25
    return (
        float((age_years < YOUNG_YEARS).mean()),
        float((age_years >= MATURE_YEARS).mean()),
        len(alive),
        age_years,
    )


@register_indicator
class AgeMix:
    id = "age_mix"
    label = "업력 구성"
    requires = frozenset({"moi"})

    @staticmethod
    def fmt(value: float) -> str:
        return f"신생 {value * 100:.0f}%"

    def compute(self, ctx: AreaContext) -> IndicatorResult:
        young, mature, n_alive, age_years = _shares(ctx.establishments, ctx.now)

        series = None
        if age_years is not None:
            rows = []
            for lo, hi, label in _BUCKETS:
                count = int(((age_years >= lo) & (age_years < hi)).sum())
                rows.append({"업력구간": label, "업소수": count})
            series = pd.DataFrame(rows)

        percentile = None
        if ctx.reference is not None and young is not None:
            percentile = grid_percentile(
                ctx.reference, lambda cell: _shares(cell, ctx.now)[0], young
            )
        return IndicatorResult(
            current=young if young is not None else float("nan"),
            previous=None,  # 구성비라 '직전 기간' 비교 대신 percentile로 상대화한다
            series=series,
            percentile=percentile,
            fact=(
                f"영업중 {n_alive}곳 — 업력 2년 미만 {young * 100:.0f}%, 7년 이상 {mature * 100:.0f}%"
                if young is not None
                else "반경 내 영업중 업소가 없습니다"
            ),
        )

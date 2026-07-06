"""순증 모멘텀 — 최근 12개월 (개업−폐업)/활성업소, 직전 12개월 대비"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import grid_percentile
from signals.registry import register_indicator


def _momentum(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, int, int]:
    """(모멘텀, 개업수, 폐업수). 모멘텀 = 순증/활성업소 — 상권 크기 차이를 정규화."""
    opened = int(df[schema.LICENSED_AT].between(start, end).sum())
    closed = int(df[schema.CLOSED_AT].between(start, end).sum())
    active = max(int(df[schema.IS_OPEN].sum()), 1)
    return (opened - closed) / active, opened, closed


@register_indicator
class NetMomentum:
    id = "net_momentum"
    label = "순증 모멘텀"
    requires = frozenset({"moi"})

    @staticmethod
    def fmt(value: float) -> str:
        return f"{value * 100:+.1f}%"

    def compute(self, ctx: AreaContext) -> IndicatorResult:
        df = ctx.establishments
        now = ctx.now
        current, opened, closed = _momentum(df, now - pd.DateOffset(months=12), now)
        previous, _, _ = _momentum(df, now - pd.DateOffset(months=24), now - pd.DateOffset(months=12))

        # 36개월 월별 시계열 (차트용)
        months = pd.period_range(now - pd.DateOffset(months=35), now, freq="M")
        opened_m = df[schema.LICENSED_AT].dt.to_period("M").value_counts()
        closed_m = df[schema.CLOSED_AT].dropna().dt.to_period("M").value_counts()
        series = pd.DataFrame(
            {
                "월": [str(m) for m in months],
                "개업": [int(opened_m.get(m, 0)) for m in months],
                "폐업": [int(closed_m.get(m, 0)) for m in months],
            }
        )
        series["순증"] = series["개업"] - series["폐업"]

        percentile = None
        if ctx.reference is not None:
            percentile = grid_percentile(
                ctx.reference, lambda cell: _momentum(cell, now - pd.DateOffset(months=12), now)[0], current
            )
        return IndicatorResult(
            current=round(current, 4),
            previous=round(previous, 4),
            series=series,
            percentile=percentile,
            fact=f"최근 12개월 개업 {opened}·폐업 {closed} — 활성업소 대비 순증 {current * 100:+.1f}% (직전 12개월 {previous * 100:+.1f}%)",
        )

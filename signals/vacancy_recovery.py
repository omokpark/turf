"""공실 회복 속도 — 폐업한 자리에 새 인허가가 들어오기까지 걸린 일수

빈 자리가 빨리 채워지는 골목 = 들어오려는 대기 수요가 있다는 가장 직접적인 증거.
개업·폐업 수만 봐서는 안 보이는 신호다.

주의(오른쪽 절단): 아직 재입점이 안 된 폐업(공실 지속 중)은 표본에서 빠지므로
최근 기간의 중앙값은 실제보다 빨라 보이는 쪽으로 치우친다 — fact에 표본 수를 병기해
투명하게 드러낸다.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import address_key, grid_percentile
from signals.registry import register_indicator


def _refill_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """폐업 → 같은 주소의 다음 인허가까지의 간격. 반환: [폐업일자, 재입점일자, 공백일수]"""
    d = df.assign(_주소키=address_key(df))
    d = d[d["_주소키"].str.len() > 0]
    closures = (
        d.loc[d[schema.CLOSED_AT].notna(), ["_주소키", schema.CLOSED_AT]]
        .sort_values(schema.CLOSED_AT)
        .reset_index(drop=True)
    )
    licenses = (
        d.loc[d[schema.LICENSED_AT].notna(), ["_주소키", schema.LICENSED_AT]]
        .sort_values(schema.LICENSED_AT)
        .reset_index(drop=True)
    )
    if len(closures) == 0 or len(licenses) == 0:
        return pd.DataFrame(columns=["폐업일자", "재입점일자", "공백일수"])
    merged = pd.merge_asof(
        closures,
        licenses.rename(columns={schema.LICENSED_AT: "재입점일자"}),
        left_on=schema.CLOSED_AT,
        right_on="재입점일자",
        by="_주소키",
        direction="forward",
        allow_exact_matches=False,
    )
    merged = merged.dropna(subset=["재입점일자"])
    out = pd.DataFrame(
        {
            "폐업일자": merged[schema.CLOSED_AT],
            "재입점일자": merged["재입점일자"],
            "공백일수": (merged["재입점일자"] - merged[schema.CLOSED_AT]).dt.days,
        }
    )
    return out[out["공백일수"] >= 0].reset_index(drop=True)


def _median_gap(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float | None, int]:
    gaps = _refill_gaps(df)
    window = gaps[gaps["폐업일자"].between(start, end)]
    if len(window) == 0:
        return None, 0
    return float(window["공백일수"].median()), len(window)


@register_indicator
class VacancyRecovery:
    id = "vacancy_recovery"
    label = "공실 회복 속도"
    requires = frozenset({"moi"})

    @staticmethod
    def fmt(value: float) -> str:
        return f"{value:.0f}일"

    def compute(self, ctx: AreaContext) -> IndicatorResult:
        df = ctx.establishments
        now = ctx.now
        current, n_recent = _median_gap(df, now - pd.DateOffset(years=3), now)
        previous, n_prev = _median_gap(df, now - pd.DateOffset(years=6), now - pd.DateOffset(years=3))

        gaps = _refill_gaps(df)
        if len(gaps) > 0:
            series = (
                gaps.assign(연도=gaps["폐업일자"].dt.year)
                .groupby("연도")["공백일수"]
                .median()
                .reset_index(name="중앙값공백일수")
            )
        else:
            series = pd.DataFrame(columns=["연도", "중앙값공백일수"])

        percentile = None
        if ctx.reference is not None and current is not None:
            # 빠를수록(일수가 작을수록) 좋은 신호 — 부호를 뒤집어 '상위 N%'가 빠름을 뜻하게 한다
            percentile = grid_percentile(
                ctx.reference,
                lambda cell: (lambda v: -v[0] if v[0] is not None else None)(
                    _median_gap(cell, now - pd.DateOffset(years=3), now)
                ),
                -current,
            )
        prev_txt = f"{previous:.0f}일" if previous is not None else "표본 없음"
        return IndicatorResult(
            current=current if current is not None else float("nan"),
            previous=previous,
            series=series,
            percentile=percentile,
            fact=(
                f"빈 자리가 다시 채워지기까지 중앙값 {current:.0f}일 (최근 3년 재입점 {n_recent}건, "
                f"그 전 3년 {prev_txt}·{n_prev}건) — 재입점 완료 건 기준"
                if current is not None
                else f"최근 3년 내 재입점 완료 사례가 없습니다 (표본 0건)"
            ),
        )

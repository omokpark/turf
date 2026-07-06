"""공실 회복 속도 — 폐업한 자리에 새 인허가가 들어오기까지 걸린 일수

빈 자리가 빨리 채워지는 골목 = 들어오려는 대기 수요가 있다는 가장 직접적인 증거.

측정 설계 (연도 간 공정 비교를 위한 두 가지 장치):
1. 재입점 인정 기한 24개월 — 폐업 후 24개월을 넘겨 들어온 인허가는 공실 대기가
   아니라 재건축·용도 변경 등 무관한 사건일 가능성이 높아 재입점으로 치지 않는다.
   (기한 없이 재면 1995년 폐업→2015년 인허가 같은 20년 '공백'이 과거 중앙값을 부풀린다)
2. 완결 관측만 비교 — 폐업 후 24개월이 아직 안 지난 최근 폐업은 재입점 여부가
   미확정이므로 통계에서 제외한다. (안 빼면 최근 기간은 빨리 채워진 것만 관측돼
   실제보다 빨라 보인다)
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, IndicatorResult
from signals.outlook import address_key, grid_percentile
from signals.registry import register_indicator

REFILL_WINDOW_DAYS = 730  # 재입점 인정 기한 (24개월)


def _refill_observations(df: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """완결 관측된 폐업들의 재입점 여부·소요일.

    반환: [폐업일자, 공백일수(재입점 없으면 NaN), 재입점(bool)]
    완결 = 폐업일 + 24개월 ≤ today (재입점 여부가 확정된 폐업만).
    """
    d = df.assign(_주소키=address_key(df))
    d = d[d["_주소키"].str.len() > 0]
    complete_cutoff = today - pd.Timedelta(days=REFILL_WINDOW_DAYS)
    closures = (
        d.loc[d[schema.CLOSED_AT].notna() & (d[schema.CLOSED_AT] <= complete_cutoff), ["_주소키", schema.CLOSED_AT]]
        .sort_values(schema.CLOSED_AT)
        .reset_index(drop=True)
    )
    licenses = (
        d.loc[d[schema.LICENSED_AT].notna(), ["_주소키", schema.LICENSED_AT]]
        .sort_values(schema.LICENSED_AT)
        .reset_index(drop=True)
    )
    if len(closures) == 0 or len(licenses) == 0:
        return pd.DataFrame(columns=["폐업일자", "공백일수", "재입점"])
    merged = pd.merge_asof(
        closures,
        licenses.rename(columns={schema.LICENSED_AT: "재입점일자"}),
        left_on=schema.CLOSED_AT,
        right_on="재입점일자",
        by="_주소키",
        direction="forward",
        allow_exact_matches=False,
    )
    gap = (merged["재입점일자"] - merged[schema.CLOSED_AT]).dt.days
    refilled = gap.notna() & (gap >= 0) & (gap <= REFILL_WINDOW_DAYS)
    return pd.DataFrame(
        {
            "폐업일자": merged[schema.CLOSED_AT],
            "공백일수": gap.where(refilled),
            "재입점": refilled,
        }
    )


def _window_stats(obs: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float | None, float | None, int]:
    """(중앙값 공백일수, 재입점률, 완결 폐업 수) — 폐업일 기준 기간 필터."""
    window = obs[obs["폐업일자"].between(start, end)]
    if len(window) == 0:
        return None, None, 0
    refilled = window[window["재입점"]]
    median = float(refilled["공백일수"].median()) if len(refilled) > 0 else None
    return median, float(window["재입점"].mean()), len(window)


def _cell_median(cell: pd.DataFrame, today: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    median, _, _ = _window_stats(_refill_observations(cell, today), start, end)
    return -median if median is not None else None  # 빠를수록 좋음 — 부호 반전


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
        obs = _refill_observations(df, now)
        # 완결 관측만 있으므로 기간 상한은 (now - 24개월). 거기서 3년씩 두 구간.
        complete_end = now - pd.Timedelta(days=REFILL_WINDOW_DAYS)
        cur_start = complete_end - pd.DateOffset(years=3)
        prev_start = complete_end - pd.DateOffset(years=6)
        current, cur_rate, n_cur = _window_stats(obs, cur_start, complete_end)
        previous, prev_rate, n_prev = _window_stats(obs, prev_start, cur_start)

        if len(obs) > 0:
            series = (
                obs.assign(연도=obs["폐업일자"].dt.year)
                .groupby("연도")
                .agg(중앙값공백일수=("공백일수", "median"), 재입점률=("재입점", "mean"), 완결폐업수=("재입점", "size"))
                .reset_index()
            )
            series["재입점률"] = (series["재입점률"] * 100).round(1)
        else:
            series = pd.DataFrame(columns=["연도", "중앙값공백일수", "재입점률", "완결폐업수"])

        percentile = None
        if ctx.reference is not None and current is not None:
            percentile = grid_percentile(
                ctx.reference,
                lambda cell: _cell_median(cell, now, cur_start, complete_end),
                -current,
            )
        if current is not None:
            prev_txt = f"{previous:.0f}일" if previous is not None else "표본 없음"
            period = f"{cur_start.year}~{complete_end.year}년 폐업"
            fact = (
                f"폐업 후 24개월 내 재입점된 자리의 중앙값 공백 {current:.0f}일, 재입점률 {cur_rate * 100:.0f}% "
                f"({period} {n_cur}건 기준 · 직전 3년 {prev_txt}·재입점률 {prev_rate * 100:.0f}%)"
                if prev_rate is not None
                else f"폐업 후 24개월 내 재입점 중앙값 {current:.0f}일, 재입점률 {cur_rate * 100:.0f}% ({period} {n_cur}건)"
            )
        else:
            fact = f"완결 관측(폐업 후 24개월 경과)된 재입점 사례가 없습니다 (완결 폐업 {n_cur}건)"
        return IndicatorResult(
            current=current if current is not None else float("nan"),
            previous=previous,
            series=series,
            percentile=percentile,
            fact=fact,
        )

"""M0 구역 아웃룩 — 헬퍼·지표 5개의 수치 검증 (합성 명부, today 고정)"""

import pandas as pd
import pytest

from core import schema
from signals import outlook
from signals.age_mix import AgeMix
from signals.cohort_survival import CohortSurvival
from signals.liquor_shift import LiquorShift
from signals.net_momentum import NetMomentum
from signals.vacancy_recovery import VacancyRecovery
from signals.base import AreaContext
from core.area import Area
from tests.conftest import make_roster

TODAY = pd.Timestamp("2026-07-06")


def _ctx(df, reference=None):
    return AreaContext(
        area=Area(cx=127.0276, cy=37.4979, radius=800),
        establishments=df,
        rosters={"moi": df},
        reference=reference,
        today=TODAY,
    )


# ── 주류친화 분류 ─────────────────────────────────────────────────────────────
def test_liquor_classification():
    df = make_roster(
        [
            {schema.NAME: "역전할머니맥주", schema.CAT_S: "한식"},   # 이름으로 잡힘
            {schema.NAME: "장수촌", schema.CAT_S: "호프/통닭"},      # 업태로 잡힘
            {schema.NAME: "김밥천국", schema.CAT_S: "분식"},         # 둘 다 아님
        ]
    )
    flags = outlook.is_liquor_friendly(df[schema.CAT_S], df[schema.NAME])
    assert list(flags) == [True, True, False]


# ── 국면 궤적 ────────────────────────────────────────────────────────────────
def test_phase_trajectory_quadrants():
    rows = []
    # 2023: 개업2·폐업4 / 2024: 개업4·폐업2 (개업↑폐업↓=확장) / 2025: 개업6·폐업5 (개업↑폐업↑=교체)
    for y, n_open, n_close in [(2023, 2, 4), (2024, 4, 2), (2025, 6, 5)]:
        for i in range(n_open):
            rows.append({schema.LICENSED_AT: f"{y}-03-0{i % 9 + 1}"})
        for i in range(n_close):
            rows.append(
                {schema.LICENSED_AT: "2015-01-01", schema.CLOSED_AT: f"{y}-06-0{i % 9 + 1}", schema.IS_OPEN: False}
            )
    df = make_roster(rows)
    out = outlook.phase_trajectory(df, years=3, today=TODAY)
    # 올해(2026, 부분 연도)는 제외되고 첫 해(2023)는 기준선이라 2024·2025만 나온다
    assert list(out["연도"]) == [2024, 2025]
    assert out[out["연도"] == 2024].iloc[0]["국면"] == outlook.PHASE_EXPANSION
    assert out[out["연도"] == 2025].iloc[0]["국면"] == outlook.PHASE_CHURN


# ── 순증 모멘텀 ──────────────────────────────────────────────────────────────
def test_net_momentum_numbers():
    df = make_roster(
        [
            # 최근 12개월: 개업 2
            {schema.LICENSED_AT: "2026-01-15"},
            {schema.LICENSED_AT: "2025-09-01"},
            # 최근 12개월: 폐업 1
            {schema.LICENSED_AT: "2020-01-01", schema.CLOSED_AT: "2026-02-01", schema.IS_OPEN: False},
            # 오래된 영업중 2 (활성 분모에 포함)
            {schema.LICENSED_AT: "2015-01-01"},
            {schema.LICENSED_AT: "2016-01-01"},
        ]
    )
    result = NetMomentum().compute(_ctx(df))
    # 활성 = 개업2 + 기존2 = 4, 순증 = 2-1 = 1 → 0.25
    assert result.current == 0.25
    assert "개업 2·폐업 1" in result.fact
    assert len(result.series) == 36


# ── 공실 회복 속도 ────────────────────────────────────────────────────────────
def test_vacancy_recovery_gap():
    addr = "서울특별시 강남구 테스트로 1"
    df = make_roster(
        [
            # 같은 주소: 2024-01-01 폐업(완결 관측) → 2024-04-10 재입점 (100일)
            {schema.ADDR_ROAD: addr, schema.LICENSED_AT: "2020-01-01",
             schema.CLOSED_AT: "2024-01-01", schema.IS_OPEN: False},
            {schema.ADDR_ROAD: addr, schema.LICENSED_AT: "2024-04-10"},
            # 최근 폐업(2025): 24개월이 안 지나 미완결 — 통계에서 제외돼야 함
            {schema.LICENSED_AT: "2019-01-01", schema.CLOSED_AT: "2025-01-01", schema.IS_OPEN: False},
        ]
    )
    result = VacancyRecovery().compute(_ctx(df))
    assert result.current == 100.0
    assert "1건" in result.fact
    assert "재입점률 100%" in result.fact


def test_vacancy_recovery_window_cap_excludes_unrelated_relicense():
    """24개월 넘어 들어온 인허가는 재입점이 아니다 — 20년 공백이 중앙값을 부풀리던 버그의 회귀 테스트."""
    addr = "서울특별시 강남구 테스트로 2"
    df = make_roster(
        [
            # 2000-01-01 폐업 → 2015년 인허가: 15년 공백은 재입점으로 안 친다
            {schema.ADDR_ROAD: addr, schema.LICENSED_AT: "1995-01-01",
             schema.CLOSED_AT: "2000-01-01", schema.IS_OPEN: False},
            {schema.ADDR_ROAD: addr, schema.LICENSED_AT: "2015-01-01"},
        ]
    )
    result = VacancyRecovery().compute(_ctx(df))
    series = result.series
    y2000 = series[series["연도"] == 2000].iloc[0]
    assert bool(pd.isna(y2000["중앙값공백일수"]))  # 재입점 없음
    assert y2000["재입점률"] == 0.0
    assert y2000["완결폐업수"] == 1


def test_vacancy_recovery_incomplete_closures_excluded():
    """폐업 후 24개월이 안 지난 폐업은 재입점 여부 미확정 — 표본에서 빠져야 한다."""
    df = make_roster(
        [{schema.LICENSED_AT: "2019-01-01", schema.CLOSED_AT: "2026-01-01", schema.IS_OPEN: False}]
    )
    result = VacancyRecovery().compute(_ctx(df))
    assert pd.isna(result.current)
    assert "완결 폐업 0건" in result.fact
    assert len(result.series) == 0


def test_vacancy_recovery_no_samples():
    df = make_roster([{schema.LICENSED_AT: "2020-01-01"}])
    result = VacancyRecovery().compute(_ctx(df))
    assert pd.isna(result.current)
    assert "완결 폐업 0건" in result.fact


# ── 신규 생존율 ──────────────────────────────────────────────────────────────
def test_cohort_survival_rate():
    df = make_roster(
        [
            # 2024 코호트(최신 완결): 4곳 중 1곳이 1년 내 폐업 → 75%
            {schema.LICENSED_AT: "2024-03-01"},
            {schema.LICENSED_AT: "2024-05-01"},
            {schema.LICENSED_AT: "2024-07-01"},
            {schema.LICENSED_AT: "2024-02-01", schema.CLOSED_AT: "2024-11-01", schema.IS_OPEN: False},
            # 2023 코호트: 2곳 중 1곳 조기 폐업 → 50%
            {schema.LICENSED_AT: "2023-04-01"},
            {schema.LICENSED_AT: "2023-06-01", schema.CLOSED_AT: "2023-12-01", schema.IS_OPEN: False},
            # 1년 넘게 버티다 폐업한 곳은 '1년 생존'으로 집계
            {schema.LICENSED_AT: "2024-01-01", schema.CLOSED_AT: "2025-06-01", schema.IS_OPEN: False},
        ]
    )
    result = CohortSurvival().compute(_ctx(df))
    assert result.current == 0.8  # 2024 코호트 5곳 중 조기폐업 1곳
    assert result.previous == 0.5
    assert "2024년 개업 5곳" in result.fact


# ── 주류친화 전환율 ──────────────────────────────────────────────────────────
def test_liquor_shift_share():
    df = make_roster(
        [
            # 최근 2년 개업 4곳 중 주류친화 2곳 = 50%
            {schema.NAME: "새호프", schema.CAT_S: "호프/통닭", schema.LICENSED_AT: "2025-01-01"},
            {schema.NAME: "새포차", schema.CAT_S: "한식", schema.LICENSED_AT: "2025-06-01"},
            {schema.NAME: "새카페", schema.CAT_S: "까페", schema.LICENSED_AT: "2026-01-01"},
            {schema.NAME: "새분식", schema.CAT_S: "분식", schema.LICENSED_AT: "2025-03-01"},
            # 직전 2년(2022-07~2024-07) 개업 2곳 중 주류친화 0곳 = 0%
            {schema.NAME: "옛날카페", schema.CAT_S: "까페", schema.LICENSED_AT: "2023-01-01"},
            {schema.NAME: "옛날분식", schema.CAT_S: "분식", schema.LICENSED_AT: "2023-06-01"},
        ]
    )
    result = LiquorShift().compute(_ctx(df))
    assert result.current == 0.5
    assert result.previous == 0.0
    assert "신규 개업 4곳" in result.fact


# ── 업력 구성 ────────────────────────────────────────────────────────────────
def test_age_mix_shares():
    df = make_roster(
        [
            {schema.LICENSED_AT: "2026-01-01"},  # 0.5년 — 신생
            {schema.LICENSED_AT: "2025-01-01"},  # 1.5년 — 신생
            {schema.LICENSED_AT: "2022-01-01"},  # 4.5년 — 중간
            {schema.LICENSED_AT: "2015-01-01"},  # 11.5년 — 장수
            # 폐업 업소는 제외
            {schema.LICENSED_AT: "2010-01-01", schema.CLOSED_AT: "2020-01-01", schema.IS_OPEN: False},
        ]
    )
    result = AgeMix().compute(_ctx(df))
    assert result.current == 0.5   # 신생 2/4
    assert "7년 이상 25%" in result.fact
    assert result.series["업소수"].sum() == 4


# ── 격자 percentile ──────────────────────────────────────────────────────────
def test_grid_percentile_ranks_focal_value():
    # 10개 셀, 셀마다 40행 — 셀 값(영업중 비율)이 0.1, 0.2, ..., 1.0이 되게 구성
    rows = []
    for i in range(10):
        lat = 37.40 + i * 0.01  # 셀 간 ~1.1km — 500m 격자에서 확실히 분리
        alive = 4 * (i + 1)
        for j in range(40):
            rows.append(
                {
                    schema.LAT: lat,
                    schema.LON: 127.0,
                    schema.IS_OPEN: j < alive,
                    schema.LICENSED_AT: "2020-01-01",
                    **({schema.CLOSED_AT: "2023-01-01"} if j >= alive else {}),
                }
            )
    reference = make_roster(rows)
    pct = outlook.grid_percentile(reference, lambda cell: cell[schema.IS_OPEN].mean(), focal_value=0.55)
    assert pct == 50.0  # 0.1~1.0 중 0.55보다 작거나 같은 값 5개


def test_grid_percentile_insufficient_cells_returns_none():
    reference = make_roster([{schema.LAT: 37.5, schema.LON: 127.0} for _ in range(50)])
    pct = outlook.grid_percentile(reference, lambda cell: 1.0, focal_value=1.0)
    assert pct is None  # 셀 1개뿐 — 최소 8개 미만

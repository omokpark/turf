"""Phase 2b 업소 모델(M2/M4/M5) + weighted_sum 스코어러 계약·수치 검증"""

import pandas as pd
import pytest

from core.area import Area
from scorers import base as scorer_base
from scorers.weighted_sum import WeightedSum
from signals import base as signal_base
from signals.base import AreaContext
from signals.franchise import Franchise, normalize_name
from signals.liquor_adjacency import LiquorAdjacency
from signals.recent_opening import GOLDEN_WINDOW_DAYS, RecentOpening
from signals.survivor import Survivor
from tests.conftest import make_roster
from core import schema

TODAY = pd.Timestamp("2026-07-06")


def _ctx(df, reference=None):
    return AreaContext(
        area=Area(cx=127.0276, cy=37.4979, radius=800),
        establishments=df,
        rosters={"moi": df},
        reference=reference if reference is not None else df,
        today=TODAY,
    )


# ── M2 생존자 지수 ────────────────────────────────────────────────────────────
def test_survivor_output_contract(gangnam_roster):
    result = Survivor().compute(_ctx(gangnam_roster))
    signal_base.validate_signal_result(result)


def test_survivor_ranks_long_tenure_above_new_open(gangnam_roster):
    result = Survivor().compute(_ctx(gangnam_roster)).set_index(signal_base.EST_ID)
    # 장수집(2015 개업)은 신상집(2026-06 개업)보다 값이 커야 한다
    long_tenure = gangnam_roster[gangnam_roster[schema.NAME] == "장수집"][schema.SRC_ID].iloc[0]
    new_open = gangnam_roster[gangnam_roster[schema.NAME] == "신상집"][schema.SRC_ID].iloc[0]
    assert result.loc[long_tenure, signal_base.VALUE] > result.loc[new_open, signal_base.VALUE]


def test_survivor_empty_without_closure_history():
    """폐업 이력이 아예 없으면 자리 평균의 기준이 없어 계산하지 않는다."""
    df = make_roster([{schema.NAME: "혼자만있는집"}])
    result = Survivor().compute(_ctx(df))
    assert len(result) == 0


def test_survivor_site_average_shrinks_small_samples():
    """폐업 1건짜리 자리의 0.2년 평균을 그대로 쓰면 '0.2년의 10배' 같은 배지가 나온다 —
    자리평균은 표본 수만큼 지역 평균과 혼합돼야 한다 (축소추정)."""
    addr = "서울특별시 강남구 테스트로 9"
    df = make_roster(
        [
            # 이 자리: 직전 입주자가 73일(0.2년) 만에 폐업한 단 1건
            {schema.NAME: "초단명전임자", schema.ADDR_ROAD: addr, schema.LICENSED_AT: "2024-01-01",
             schema.CLOSED_AT: "2024-03-14", schema.IS_OPEN: False},
            {schema.NAME: "현재입주자", schema.ADDR_ROAD: addr, schema.LICENSED_AT: "2024-07-06"},
            # 다른 자리: 4년 버틴 폐업 — 지역 평균을 2.1년으로 끌어올린다
            {schema.NAME: "장수폐업", schema.LICENSED_AT: "2020-01-01",
             schema.CLOSED_AT: "2024-01-01", schema.IS_OPEN: False},
        ]
    )
    result = Survivor().compute(_ctx(df)).set_index(signal_base.EST_ID)
    cur_id = df[df[schema.NAME] == "현재입주자"][schema.SRC_ID].iloc[0]
    badge = result.loc[cur_id, signal_base.BADGE]
    # 원시 자리평균 0.2년이면 "0.2년의 10.0배" — 혼합 후 (0.2+2.1)/2 = 1.1년의 1.7배
    assert "0.2년" not in badge
    assert "1.1년의 1.7배" in badge


# ── M4 프랜차이즈 판별 ────────────────────────────────────────────────────────
def test_normalize_name_strips_branch_suffix():
    assert normalize_name("스타벅스 강남역점") == "스타벅스강남"
    assert normalize_name("김밥천국(2호점)") == "김밥천국"


def test_franchise_flags_repeated_name_as_chain(monkeypatch):
    # 전국 스캔 파일이 있어도 이 테스트는 폴백(수집 범위) 경로를 검증한다
    monkeypatch.setattr("signals.franchise.load_national_counts", lambda: None)
    # 괄호 안 지점 표기(정규화 시 제거됨)만 다르고 나머지가 같아야 같은 상호로 묶인다 —
    # normalize_name은 접미사만 지우는 근사치라 서로 다른 지점명이 섞이면 안 뭉친다.
    rows = [{schema.NAME: f"김밥천국({i}호점)"} for i in range(3)] + [{schema.NAME: "독립식당"}]
    df = make_roster(rows)
    result = Franchise().compute(_ctx(df)).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    chain_id = df[df[schema.NAME] == "김밥천국(0호점)"][schema.SRC_ID].iloc[0]
    indep_id = df[df[schema.NAME] == "독립식당"][schema.SRC_ID].iloc[0]
    assert result.loc[chain_id, signal_base.VALUE] == 0.0
    assert result.loc[indep_id, signal_base.VALUE] == 1.0


def test_franchise_uses_national_counts_when_available(monkeypatch):
    """전국 스캔이 있으면 동네 유일 지점의 대형 체인(써브웨이 케이스)도 잡는다."""
    national = pd.Series({"써브웨이강남": 348, "동네백반": 1})
    monkeypatch.setattr("signals.franchise.load_national_counts", lambda: national)
    monkeypatch.setattr("signals.franchise.scan_freshness", lambda: "2026-07-07")
    df = make_roster([{schema.NAME: "(주)써브웨이 강남역점"}, {schema.NAME: "동네백반"}])
    result = Franchise().compute(_ctx(df)).set_index(signal_base.EST_ID)

    chain_id = df[df[schema.NAME] == "(주)써브웨이 강남역점"][schema.SRC_ID].iloc[0]
    indep_id = df[df[schema.NAME] == "동네백반"][schema.SRC_ID].iloc[0]
    assert result.loc[chain_id, signal_base.VALUE] == 0.0
    assert "전국" in result.loc[chain_id, signal_base.BADGE] and "348" in result.loc[chain_id, signal_base.BADGE]
    assert result.loc[indep_id, signal_base.VALUE] == 1.0
    assert pd.isna(result.loc[indep_id, signal_base.BADGE])


# ── M5 주류 인접성 지수 ───────────────────────────────────────────────────────
def test_liquor_adjacency_counts_nearby_liquor_shops():
    # make_roster 기본 좌표는 모든 행이 동일 — 명시적으로 다르게 준 행만 떨어져 있다
    rows = [
        {schema.NAME: "호프집", schema.CAT_S: "호프/통닭"},
        {schema.NAME: "옆식당", schema.CAT_S: "한식"},
        {schema.NAME: "멀리떨어진집", schema.CAT_S: "한식", schema.LAT: 37.55},  # 반경 밖
    ]
    df = make_roster(rows)
    result = LiquorAdjacency().compute(_ctx(df)).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    nearby_id = df[df[schema.NAME] == "옆식당"][schema.SRC_ID].iloc[0]
    far_id = df[df[schema.NAME] == "멀리떨어진집"][schema.SRC_ID].iloc[0]
    assert result.loc[nearby_id, signal_base.RAW] == 1  # 같은 좌표의 호프집 1곳
    assert far_id not in result.index or result.loc[far_id, signal_base.RAW] == 0


# ── 신규 개업 골든타임 ────────────────────────────────────────────────────────
def test_recent_opening_decays_with_days(gangnam_roster):
    result = RecentOpening().compute(_ctx(gangnam_roster)).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    new_id = gangnam_roster[gangnam_roster[schema.NAME] == "신상집"][schema.SRC_ID].iloc[0]  # 2026-06-01 개업
    old_id = gangnam_roster[gangnam_roster[schema.NAME] == "장수집"][schema.SRC_ID].iloc[0]  # 2015 개업
    assert result.loc[new_id, signal_base.VALUE] == pytest.approx(1 - 35 / GOLDEN_WINDOW_DAYS, abs=0.01)
    assert result.loc[new_id, signal_base.BADGE].startswith("🆕 개업 35일차")
    # 창 밖 업소도 행은 있되(재정규화 균형용) 값 0 · 배지 없음 (None은 NaN으로 변환될 수 있음)
    assert result.loc[old_id, signal_base.VALUE] == 0.0
    assert pd.isna(result.loc[old_id, signal_base.BADGE])


# ── weighted_sum 스코어러 ────────────────────────────────────────────────────
def _signal_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=signal_base.SIGNAL_COLUMNS)


def test_weighted_sum_averages_available_signals():
    # DEFAULT_WEIGHTS에 없는 id를 써서 순수 평균 동작을 검증한다 (둘 다 FALLBACK_WEIGHT)
    results = {
        "sig_a": _signal_df(
            [{signal_base.EST_ID: "A", signal_base.VALUE: 1.0, signal_base.RAW: 1, signal_base.BADGE: "b1", signal_base.DETAIL: ""}]
        ),
        "sig_b": _signal_df(
            [{signal_base.EST_ID: "A", signal_base.VALUE: 0.0, signal_base.RAW: 1, signal_base.BADGE: "b2", signal_base.DETAIL: ""}]
        ),
    }
    scored = WeightedSum().score(results, ctx=None)
    scorer_base.validate_score_result(scored)
    row = scored[scored[scorer_base.EST_ID] == "A"].iloc[0]
    assert row[scorer_base.SCORE] == pytest.approx(0.5)  # 가중치 동일 → 단순 평균
    assert set(row[scorer_base.BADGES]) == {"b1", "b2"}


def test_weighted_sum_zero_weight_signal_is_badge_only():
    """franchise(가중치 0)는 점수에 영향 없이 배지만 보탠다."""
    results = {
        "sig_a": _signal_df(
            [{signal_base.EST_ID: "A", signal_base.VALUE: 1.0, signal_base.RAW: 1, signal_base.BADGE: "b1", signal_base.DETAIL: ""}]
        ),
        "franchise": _signal_df(
            [{signal_base.EST_ID: "A", signal_base.VALUE: 0.0, signal_base.RAW: 5, signal_base.BADGE: "체인 추정", signal_base.DETAIL: ""}]
        ),
    }
    scored = WeightedSum().score(results, ctx=None)
    row = scored[scored[scorer_base.EST_ID] == "A"].iloc[0]
    assert row[scorer_base.SCORE] == pytest.approx(1.0)  # franchise 0점이 평균을 깎지 않음
    assert "체인 추정" in row[scorer_base.BADGES]


def test_weighted_sum_drops_entities_without_badges():
    results = {
        "liquor_adjacency": _signal_df(
            [{signal_base.EST_ID: "A", signal_base.VALUE: 0.0, signal_base.RAW: 0, signal_base.BADGE: None, signal_base.DETAIL: ""}]
        ),
    }
    scored = WeightedSum().score(results, ctx=None)
    scorer_base.validate_score_result(scored)
    assert len(scored) == 0

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


# ── M4 프랜차이즈 판별 ────────────────────────────────────────────────────────
def test_normalize_name_strips_branch_suffix():
    assert normalize_name("스타벅스 강남역점") == "스타벅스강남"
    assert normalize_name("김밥천국(2호점)") == "김밥천국"


def test_franchise_flags_repeated_name_as_chain():
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

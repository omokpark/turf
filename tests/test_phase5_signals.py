"""Phase 5 신호(M3 성장 모멘텀, M6 업종 전환 벡터) + 주소키 강화 검증"""

import pandas as pd

from core import schema
from core.area import Area
from signals import outlook
from signals.base import AreaContext, validate_signal_result, BADGE, EST_ID, VALUE
from signals.conversion_vector import ConversionVector
from signals.growth_momentum import GrowthMomentum
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


# ── 주소키 강화 ──────────────────────────────────────────────────────────────
def test_address_key_strips_legal_dong_annotation():
    df = make_roster(
        [
            {schema.ADDR_ROAD: "서울특별시 강남구 강남대로 390, 2층 (역삼동)"},
            {schema.ADDR_ROAD: "서울특별시 강남구 강남대로 390,2층"},
        ]
    )
    keys = outlook.address_key(df)
    assert keys.iloc[0] == keys.iloc[1] == "서울특별시 강남구 강남대로 390,2층"


def test_address_key_keeps_unit_level():
    """층·호 정보는 유지 — 건물 전체를 하나의 자리로 뭉개면 자리회전이 과대 계산된다."""
    df = make_roster(
        [
            {schema.ADDR_ROAD: "서울특별시 강남구 강남대로 390, 1층"},
            {schema.ADDR_ROAD: "서울특별시 강남구 강남대로 390, 2층"},
        ]
    )
    keys = outlook.address_key(df)
    assert keys.iloc[0] != keys.iloc[1]


# ── 주류친화도 점수표 ─────────────────────────────────────────────────────────
def test_liquor_affinity_scale():
    assert outlook.liquor_affinity("유흥주점", "아무개") == 3
    assert outlook.liquor_affinity("호프/통닭", "장수통닭") == 2
    assert outlook.liquor_affinity("한식", "역전할머니맥주") == 2  # 상호 키워드 보정
    assert outlook.liquor_affinity("한식", "백반집") == 1
    assert outlook.liquor_affinity("까페", "조용한커피") == 0


# ── M6 업종 전환 벡터 ─────────────────────────────────────────────────────────
def test_conversion_vector_cafe_to_hof():
    addr = "서울특별시 강남구 전환로 1"
    df = make_roster(
        [
            # 직전 입주자: 카페(0), 2024-06 폐업
            {schema.NAME: "옛카페", schema.CAT_S: "까페", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2020-01-01", schema.CLOSED_AT: "2024-06-01", schema.IS_OPEN: False},
            # 현재: 호프(2), 2024-09 개업 → Δ+2
            {schema.NAME: "새호프", schema.CAT_S: "호프/통닭", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2024-09-01"},
        ]
    )
    result = ConversionVector().compute(_ctx(df))
    validate_signal_result(result)
    assert len(result) == 1
    row = result.iloc[0]
    assert row[VALUE] == round(2 / 3, 4)
    assert "까페→호프/통닭" in row[BADGE]


def test_conversion_vector_reverse_direction_no_badge():
    """호프→카페(주류친화 하락)는 값 0·배지 없음 — 반대 방향은 신호가 아니다."""
    addr = "서울특별시 강남구 전환로 2"
    df = make_roster(
        [
            {schema.NAME: "옛호프", schema.CAT_S: "호프/통닭", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2018-01-01", schema.CLOSED_AT: "2023-01-01", schema.IS_OPEN: False},
            {schema.NAME: "새카페", schema.CAT_S: "까페", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2023-05-01"},
        ]
    )
    result = ConversionVector().compute(_ctx(df))
    assert result.iloc[0][VALUE] == 0.0
    assert pd.isna(result.iloc[0][BADGE])


def test_conversion_vector_no_predecessor_excluded():
    """직전 입주자가 없는 업소(신축 등)는 결과에 포함되지 않는다."""
    df = make_roster(
        [
            {schema.NAME: "신축집", schema.LICENSED_AT: "2024-01-01"},
            # 다른 주소의 폐업 — 매칭되면 안 됨
            {schema.NAME: "무관한폐업", schema.LICENSED_AT: "2019-01-01",
             schema.CLOSED_AT: "2023-01-01", schema.IS_OPEN: False},
        ]
    )
    result = ConversionVector().compute(_ctx(df))
    assert len(result) == 0


def test_conversion_vector_picks_most_recent_predecessor():
    """같은 주소에 폐업이 여럿이면 이 업소 개업 직전 것을 쓴다."""
    addr = "서울특별시 강남구 전환로 3"
    df = make_roster(
        [
            {schema.NAME: "아주옛날유흥", schema.CAT_S: "유흥주점", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2010-01-01", schema.CLOSED_AT: "2015-01-01", schema.IS_OPEN: False},
            {schema.NAME: "직전분식", schema.CAT_S: "분식", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2016-01-01", schema.CLOSED_AT: "2023-01-01", schema.IS_OPEN: False},
            {schema.NAME: "현재주점", schema.CAT_S: "감성주점", schema.ADDR_ROAD: addr,
             schema.LICENSED_AT: "2023-06-01"},
        ]
    )
    result = ConversionVector().compute(_ctx(df))
    row = result.iloc[0]
    assert "직전분식" in row["상세"]  # 유흥주점(3)이 아니라 직전 분식(0) 기준
    assert row[VALUE] == round(2 / 3, 4)  # 0→2


# ── M3 상권 성장 모멘텀 ───────────────────────────────────────────────────────
def _cell_rows(lat, n_recent, n_prev, n_old_active, name_prefix):
    """한 격자 셀의 합성 구성: 최근 12M 개업 n_recent, 직전 12M n_prev, 오래된 활성 n_old_active."""
    rows = []
    for i in range(n_recent):
        rows.append({schema.NAME: f"{name_prefix}신규{i}", schema.LAT: lat, schema.LON: 127.0,
                     schema.LICENSED_AT: "2026-01-15"})
    for i in range(n_prev):
        rows.append({schema.NAME: f"{name_prefix}직전{i}", schema.LAT: lat, schema.LON: 127.0,
                     schema.LICENSED_AT: "2025-01-15"})
    for i in range(n_old_active):
        rows.append({schema.NAME: f"{name_prefix}기존{i}", schema.LAT: lat, schema.LON: 127.0,
                     schema.LICENSED_AT: "2018-01-01"})
    return rows


def test_growth_momentum_hot_cell_beats_cold_cell():
    # 뜨는 셀(개업 8→2 가속... 아니 2→8) vs 식는 셀(8→2), 둘 다 활성 충분
    hot_lat, cold_lat = 37.40, 37.45  # ~5.5km 분리 — 500m 격자에서 다른 셀
    reference = make_roster(
        _cell_rows(hot_lat, n_recent=8, n_prev=2, n_old_active=10, name_prefix="핫")
        + _cell_rows(cold_lat, n_recent=2, n_prev=8, n_old_active=10, name_prefix="콜드")
    )
    result = GrowthMomentum().compute(_ctx(reference, reference=reference))
    validate_signal_result(result)
    by_name = reference.set_index(schema.SRC_ID)[schema.NAME]
    result = result.assign(_이름=result[EST_ID].map(by_name))
    hot_value = result[result["_이름"] == "핫기존0"].iloc[0][VALUE]
    cold_value = result[result["_이름"] == "콜드기존0"].iloc[0][VALUE]
    assert hot_value > cold_value
    # 뜨는 셀 배지에 개업 수가 관측 사실로 담긴다
    hot_badge = result[result["_이름"] == "핫신규0"].iloc[0][BADGE]
    assert "12개월 개업 8곳" in hot_badge


def test_growth_momentum_small_cell_neutral():
    """활성 5곳 미만 격자는 중립(값 0, 배지 없음) — 소표본 폭주 방지."""
    reference = make_roster(_cell_rows(37.40, n_recent=2, n_prev=0, n_old_active=1, name_prefix="소"))
    result = GrowthMomentum().compute(_ctx(reference, reference=reference))
    assert (result[VALUE] == 0.0).all()
    assert result[BADGE].isna().all()

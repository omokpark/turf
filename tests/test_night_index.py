"""M7 야간 상권 지수 v1 — 서울 API는 monkeypatch, 주류친화 비중·강등 동작 검증"""

import pandas as pd
import pytest

from core import schema
from core.area import Area
from signals import base as signal_base
from signals.base import AreaContext
from signals.night_index import NightIndex
from tests.conftest import make_roster

TODAY = pd.Timestamp("2026-07-06")
NIGHT = {"비율": 0.63, "심야평균": 59558.7, "전일평균": 94550.8, "기준일": "20260620"}


def _ctx(df):
    return AreaContext(
        area=Area(cx=127.0276, cy=37.4979, radius=400),
        establishments=df,
        rosters={"moi": df},
        today=TODAY,
    )


@pytest.fixture
def seoul_ok(monkeypatch):
    monkeypatch.setattr("signals.night_index.seoul.dong_of", lambda cx, cy: ("11680640", "역삼1동"))
    monkeypatch.setattr("signals.night_index.seoul.night_population_share", lambda code: NIGHT)


def test_night_index_ranks_liquor_dense_spots(seoul_ok):
    rows = []
    # 술 골목: 호프 5 + 한식 1 (주류친화 비중 5/6)
    for i in range(5):
        rows.append({schema.NAME: f"호프{i}", schema.CAT_S: "호프/통닭", schema.LAT: 37.4979, schema.LON: 127.0276})
    rows.append({schema.NAME: "골목식당", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0276})
    # 조용한 블록: 한식만 6 (비중 0) — 400m 반경 안, 술 골목에서 ~350m 동쪽
    for i in range(6):
        rows.append({schema.NAME: f"백반{i}", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0316})
    df = make_roster(rows)

    result = NightIndex().compute(_ctx(df)).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}
    assert result.loc[ids["골목식당"], signal_base.VALUE] > result.loc[ids["백반0"], signal_base.VALUE]
    assert result.loc[ids["골목식당"], signal_base.RAW] == pytest.approx(5 / 6, abs=0.01)
    # 값에는 심야 비율이 곱해진다 (최대가 night_factor를 넘지 못함)
    assert result[signal_base.VALUE].max() <= NIGHT["비율"] + 1e-6
    # 배지는 상위 구간에만, 사실만 포함
    badge = result.loc[ids["골목식당"], signal_base.BADGE]
    assert "주류친화 비중 83%" in badge and "역삼1동" in badge


def test_night_index_degrades_outside_seoul(monkeypatch):
    monkeypatch.setattr("signals.night_index.seoul.dong_of", lambda cx, cy: None)
    df = make_roster([{schema.NAME: "부산집", schema.CAT_S: "호프/통닭"}])
    result = NightIndex().compute(_ctx(df))
    assert len(result) == 0  # 서울 밖 — 우아한 강등, 예외 없음

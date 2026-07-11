"""지도 탭 표시 프레임 — 주류 가능 필터 + 신규/폐업/영업 분류 (합성 명부)"""

import pandas as pd

from core import schema
from tests.conftest import make_roster
from ui.pages import explore


def _roster():
    return make_roster(
        [
            {schema.NAME: "호프집", schema.CAT_S: "호프/통닭", schema.LICENSED_AT: "2015-01-01"},   # 영업, affinity 2
            {schema.NAME: "한식당", schema.CAT_S: "한식", schema.LICENSED_AT: "2015-01-01"},        # 영업, affinity 1
            {schema.NAME: "카페", schema.CAT_S: "카페", schema.LICENSED_AT: "2015-01-01"},          # affinity 0 → 제외
            {schema.NAME: "새술집", schema.CAT_S: "호프/통닭", schema.LICENSED_AT: "2026-06-20"},   # 신규(골든타임)
            {schema.NAME: "최근망한집", schema.CAT_S: "한식", schema.LICENSED_AT: "2020-01-01",
             schema.CLOSED_AT: "2026-05-20", schema.IS_OPEN: False},                                # 최근 폐업
            {schema.NAME: "옛날망한집", schema.CAT_S: "한식", schema.LICENSED_AT: "2010-01-01",
             schema.CLOSED_AT: "2018-01-01", schema.IS_OPEN: False},                                # 오래전 폐업 → 제외
        ]
    )


def test_build_display_affinity1_classifies(monkeypatch):
    monkeypatch.setattr(explore.trend.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp("2026-07-06")))
    d = explore._build_display(_roster(), 127.0276, 37.4979, 400, affinity_min=1)
    by = dict(zip(d[schema.NAME], d["상태"]))
    assert by.get("호프집") == "영업" and by.get("한식당") == "영업"
    assert by.get("새술집") == "신규"
    assert by.get("최근망한집") == "폐업"
    assert "카페" not in by          # affinity 0 — 주류 무관, 제외
    assert "옛날망한집" not in by     # 오래전 폐업 — 지도에서 제외


def test_build_display_affinity2_excludes_plain_food(monkeypatch):
    monkeypatch.setattr(explore.trend.pd.Timestamp, "today", staticmethod(lambda: pd.Timestamp("2026-07-06")))
    d = explore._build_display(_roster(), 127.0276, 37.4979, 400, affinity_min=2)
    names = set(d[schema.NAME])
    assert "호프집" in names and "새술집" in names  # 주류 중심
    assert "한식당" not in names                     # affinity 1 — 주류 중심 아님, 제외

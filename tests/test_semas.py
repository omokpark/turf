"""SEMAS Provider 골든 테스트 — Provider 경유 == 기존 직접 호출 (Phase 3 전환 검증)

네트워크 없이 검증한다: fetch_shops를 합성 응답으로 대체하고, 기존 직접 호출 경로가
내던 집계 수치(test_terrain의 기준선과 동일)가 Provider→ROSTER→analyze 경로에서도
그대로 나오는지 확인한다.
"""

from datetime import timedelta

import pandas as pd
import pytest

from analyzer.terrain import analyze
from core import schema
from core.area import Area
from datasources import cache, semas

RAW_SHOPS = [
    {"상호": "한식1", "상권업종대분류명": "음식", "상권업종중분류명": "한식", "상권업종소분류명": "한식",
     "도로명주소": "서울 강남구 A", "위도": 37.4979, "경도": 127.0276},
    {"상호": "한식2", "상권업종대분류명": "음식", "상권업종중분류명": "한식", "상권업종소분류명": "한식",
     "도로명주소": "서울 강남구 B", "위도": 37.4980, "경도": 127.0277},
    {"상호": "카페1", "상권업종대분류명": "음식", "상권업종중분류명": "커피", "상권업종소분류명": "카페",
     "도로명주소": "서울 강남구 C", "위도": 37.4981, "경도": 127.0278},
    {"상호": "옷가게", "상권업종대분류명": "소매", "상권업종중분류명": "의류", "상권업종소분류명": "의류",
     "도로명주소": "서울 강남구 D", "위도": 37.4982, "경도": 127.0279},
]

AREA = Area(cx=127.0276, cy=37.4979, radius=450)


def test_to_roster_is_valid_and_faithful():
    roster = semas.to_roster(RAW_SHOPS)
    schema.validate_roster(roster)  # ROSTER 계약 통과
    assert list(roster[schema.NAME]) == ["한식1", "한식2", "카페1", "옷가게"]
    assert list(roster[schema.CAT_S]) == ["한식", "한식", "카페", "의류"]
    assert roster[schema.IS_OPEN].all()  # SEMAS는 영업 중 스냅샷
    assert roster[schema.LICENSED_AT].isna().all()  # 인허가 정보 없음 — NaT


def test_golden_provider_equals_direct_call(monkeypatch):
    """직접 호출 경로의 집계 수치가 Provider 경유에서도 동일해야 한다."""
    monkeypatch.setattr(semas, "fetch_shops", lambda cx, cy, radius: RAW_SHOPS)
    provider = semas.SemasProvider()

    direct = analyze(semas.to_roster(RAW_SHOPS))       # 기존 경로 등가물 (어댑터 직접)
    via_provider = analyze(provider.fetch(AREA))        # Provider 경유

    assert via_provider["total"] == direct["total"] == 3
    pd.testing.assert_frame_equal(via_provider["by_category"], direct["by_category"])
    top = via_provider["by_category"].iloc[0]
    assert top[schema.CAT_S] == "한식" and top["개수"] == 2


def test_fetch_cached_reuses_grid_cell(monkeypatch, tmp_path):
    """격자 캐시: 같은 셀 안의 두 지점은 재호출 없이 캐시를 재사용한다."""
    calls = []

    class FakeProvider:
        id = "fake_semas"
        kind = "roster"
        cache_ttl = timedelta(minutes=5)

        def fetch(self, area):
            calls.append(area)
            return semas.to_roster(RAW_SHOPS)

    monkeypatch.setattr(cache.config, "CACHE_DIR", tmp_path)
    provider = FakeProvider()

    df1 = cache.fetch_cached(provider, AREA)
    # 몇 m 옆 — 30m 격자에서 같은 셀
    df2 = cache.fetch_cached(provider, Area(cx=AREA.cx + 0.00002, cy=AREA.cy + 0.00002, radius=450))

    assert len(calls) == 1  # 두 번째는 파일 캐시 히트
    pd.testing.assert_frame_equal(df1, df2)


def test_fetch_cached_expires_after_ttl(monkeypatch, tmp_path):
    calls = []

    class FakeProvider:
        id = "fake_semas_ttl"
        kind = "roster"
        cache_ttl = timedelta(seconds=0)  # 즉시 만료

        def fetch(self, area):
            calls.append(area)
            return semas.to_roster(RAW_SHOPS)

    monkeypatch.setattr(cache.config, "CACHE_DIR", tmp_path)
    provider = FakeProvider()
    cache.fetch_cached(provider, AREA)
    cache.fetch_cached(provider, AREA)
    assert len(calls) == 2  # TTL 0 — 항상 재조회

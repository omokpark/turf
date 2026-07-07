"""Places 쿼터 원장 — 무료 한도 하드 스톱이 실제로 호출을 막는지 (HTTP는 monkeypatch)"""

from datetime import datetime

import pytest

from datasources import places, places_quota
from datasources.places_quota import QuotaExceeded


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(places_quota, "LEDGER_PATH", tmp_path / "ledger.json")
    return tmp_path


def test_reserve_blocks_at_safety_cap(ledger):
    """Enterprise 무료 1,000건 → 캡 900. 900번째까지 허용, 901번째 거부."""
    cap = places_quota.cap_of("place_details_enterprise")
    assert cap == 900
    places_quota.reserve("place_details_enterprise", n=cap)  # 900건 일괄 예약
    assert places_quota.remaining("place_details_enterprise") == 0
    with pytest.raises(QuotaExceeded):
        places_quota.reserve("place_details_enterprise")


def test_unlimited_sku_never_blocks(ledger):
    for _ in range(3):
        places_quota.reserve("text_search_ids_only", n=100_000)
    assert places_quota.remaining("text_search_ids_only") is None  # 무제한


def test_ledger_resets_by_month(ledger):
    june = datetime(2026, 6, 15)
    july = datetime(2026, 7, 15)
    places_quota.reserve("place_details_enterprise", n=900, now=june)
    with pytest.raises(QuotaExceeded):
        places_quota.reserve("place_details_enterprise", now=june)
    places_quota.reserve("place_details_enterprise", now=july)  # 새 달 — 다시 허용
    assert places_quota.used("place_details_enterprise", now=july) == 1


def test_unknown_sku_rejected(ledger):
    with pytest.raises(ValueError):
        places_quota.reserve("nearby_search")  # 등록 안 된 SKU는 실수 방지 차원에서 거부


def test_place_snapshot_blocked_after_cap_without_http(ledger, tmp_path, monkeypatch):
    """한도 도달 후에는 HTTP 자체가 발생하지 않아야 한다 (과금 방지의 최종 목적)."""
    monkeypatch.setattr(places.config, "CACHE_DIR", tmp_path)  # 캐시 미스 강제
    http_calls = []
    monkeypatch.setattr(places, "_get", lambda url, mask: http_calls.append(url) or {"id": "x"})

    places_quota.reserve("place_details_enterprise", n=places_quota.cap_of("place_details_enterprise"))
    with pytest.raises(QuotaExceeded):
        places.place_snapshot("ChIJtest123")
    assert http_calls == []  # 원장이 막았으므로 네트워크 접근 없음


def test_cache_hit_consumes_no_quota(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr(places.config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(places, "_get", lambda url, mask: {"id": "x", "rating": 4.4})

    places.place_snapshot("ChIJcached")
    used_after_first = places_quota.used("place_details_enterprise")
    places.place_snapshot("ChIJcached")  # 두 번째 — 30일 캐시 히트
    assert places_quota.used("place_details_enterprise") == used_after_first == 1


def test_business_status_uses_pro_quota_not_enterprise(ledger, tmp_path, monkeypatch):
    """M2 폐업 교차검증(businessStatus)은 Pro 원장을 쓴다 — Enterprise 쿼터 보존."""
    monkeypatch.setattr(places.config, "CACHE_DIR", tmp_path)
    masks = []

    def fake_get(url, mask):
        masks.append(mask)
        return {"id": "x", "businessStatus": "CLOSED_PERMANENTLY"}

    monkeypatch.setattr(places, "_get", fake_get)
    status = places.business_status("ChIJclosed")
    assert status == "CLOSED_PERMANENTLY"
    assert masks == ["id,businessStatus"]  # Enterprise 필드가 마스크에 없어야 Pro 과금
    assert places_quota.used("place_details_pro") == 1
    assert places_quota.used("place_details_enterprise") == 0

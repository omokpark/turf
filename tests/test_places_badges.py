"""Places 응답 해석 헬퍼 — 심야영업 판정·배지 문구 (Phase 6)"""

from datasources.places import is_late_night, snapshot_badges, status_badge


def _hours(periods):
    return {"periods": periods}


# ── 심야영업 판정 ─────────────────────────────────────────────────────────────
def test_late_night_by_closing_hour():
    assert is_late_night(_hours([{"open": {"day": 1, "hour": 17}, "close": {"day": 1, "hour": 23}}]))
    assert not is_late_night(_hours([{"open": {"day": 1, "hour": 10}, "close": {"day": 1, "hour": 21}}]))


def test_late_night_by_midnight_rollover():
    # 금요일 저녁 → 토요일 새벽 2시 마감
    assert is_late_night(_hours([{"open": {"day": 5, "hour": 18}, "close": {"day": 6, "hour": 2}}]))


def test_late_night_24h_no_close():
    assert is_late_night(_hours([{"open": {"day": 0, "hour": 0}}]))  # close 없음 = 24시간


def test_late_night_empty_or_missing():
    assert not is_late_night(None)
    assert not is_late_night({})


# ── 배지 문구 ─────────────────────────────────────────────────────────────────
def test_snapshot_badges_full():
    snap = {
        "businessStatus": "OPERATIONAL",
        "rating": 4.4,
        "userRatingCount": 213,
        "regularOpeningHours": _hours([{"open": {"day": 5, "hour": 18}, "close": {"day": 6, "hour": 2}}]),
    }
    badges = snapshot_badges(snap)
    assert "⭐ 구글 평점 4.4 (리뷰 213개)" in badges
    assert any(b.startswith("🌃 심야 영업") for b in badges)
    assert not any("폐업" in b for b in badges)  # 영업 중이면 경고 없음


def test_snapshot_badges_closed_and_sparse():
    badges = snapshot_badges({"businessStatus": "CLOSED_PERMANENTLY"})  # 평점·리뷰 없음
    assert badges == ["⚠️ 구글 기준 폐업 — 헛걸음 주의 (인허가 폐업신고 지연 가능)"]
    assert snapshot_badges(None) == []


def test_status_badge_variants():
    assert status_badge("OPERATIONAL") is None
    assert "임시 휴업" in status_badge("CLOSED_TEMPORARILY")
    assert status_badge(None) is None

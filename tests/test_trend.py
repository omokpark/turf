"""timeline/trend.py 5개 함수 — ROSTER 스키마 명부로 동작 검증

trend.py는 구 license_fetcher 스키마를 전제로 작성됐지만, 그 컬럼명(인허가일자·
폐업일자·영업중·주소·좌표)이 core.schema ROSTER와 동일하므로 그대로 호환된다.
이 테스트가 그 호환성의 회귀 감시자다 — Phase 2에서 신호로 이식할 때의 기준선.
"""

from core import schema
from timeline.trend import (
    business_age,
    filter_radius,
    recent_closings,
    recent_openings,
    site_turnover,
    yearly_trend,
)


def test_filter_radius(gangnam_roster):
    df = gangnam_roster.dropna(subset=[schema.LAT])
    out = filter_radius(df, cx=127.0276, cy=37.4979, radius=300)
    assert "반경밖" not in set(out[schema.NAME])
    assert len(out) == len(df) - 1


def test_yearly_trend_counts(gangnam_roster, today):
    out = yearly_trend(gangnam_roster, years=3, today=today)
    assert list(out["연도"]) == [2024, 2025, 2026]
    y2025 = out[out["연도"] == 2025].iloc[0]
    assert y2025["개업"] == 1  # 작년개업
    assert y2025["폐업"] == 1  # 작년폐업
    assert y2025["순증"] == 0
    y2026 = out[out["연도"] == 2026].iloc[0]
    assert y2026["개업"] == 2  # 신상집 + 좌표없는신규


def test_recent_openings_golden_time(gangnam_roster, today):
    out = recent_openings(gangnam_roster, days=90, today=today)
    names = list(out[schema.NAME])
    assert "신상집" in names and "좌표없는신규" in names
    assert "장수집" not in names
    # 최신 개업이 먼저
    assert names[0] == "좌표없는신규"
    assert (out["개업경과일"] >= 0).all()


def test_recent_closings(gangnam_roster, today):
    # 작년폐업(2025-08-01)은 today(2026-07-06) 기준 약 340일 전 — days를 넉넉히 줘야 잡힘
    out = recent_closings(gangnam_roster, days=400, today=today)
    names = list(out[schema.NAME])
    assert "작년폐업" in names
    assert "신상집" not in names  # 영업중 업소는 제외
    assert (out["폐업경과일"] >= 0).all()
    # 최근 폐업 90일로 좁히면 작년폐업은 빠진다
    assert len(recent_closings(gangnam_roster, days=90, today=today)) == 0


def test_site_turnover_counts_closures_at_same_address(gangnam_roster):
    out = site_turnover(gangnam_roster)
    survivor = out[out[schema.NAME] == "생존자"]
    assert len(survivor) == 1
    assert survivor.iloc[0]["자리회전수"] == 2  # 망한집1, 망한집2
    # 폐업 이력 없는 주소의 영업중 업소는 결과에 없음
    assert "장수집" not in set(out[schema.NAME])


def test_business_age(gangnam_roster, today):
    out = business_age(gangnam_roster, today=today)
    ages = dict(zip(out[schema.NAME], out["업력년"]))
    assert ages["장수집"] == 11.3  # 2015-03-01 → 2026-07-06
    assert ages["신상집"] == 0.1
    assert "망한집1" not in ages  # 폐업 업소 제외

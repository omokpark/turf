"""analyzer/terrain.analyze — 기존 동작의 회귀 기준선 (Phase 3에서 schema 상수로 전환)"""

from analyzer.terrain import analyze
from core import schema


def _shop(name, small_cat, large="음식"):
    return {
        schema.NAME: name,
        schema.CAT_L: large,
        schema.CAT_M: "",
        schema.CAT_S: small_cat,
        schema.ADDR_ROAD: "서울 강남구",
        schema.LAT: 37.5,
        schema.LON: 127.0,
    }


SHOPS = [
    _shop("한식1", "한식"),
    _shop("한식2", "한식"),
    _shop("한식3", "한식"),
    _shop("카페1", "카페"),
    _shop("호프1", "호프/맥주"),
    _shop("옷가게", "의류", large="소매"),  # 음식 아님 — 제외돼야 함
]


def test_analyze_counts_food_only():
    result = analyze(SHOPS)
    assert result["total"] == 5
    top = result["by_category"].iloc[0]
    assert top[schema.CAT_S] == "한식"
    assert top["개수"] == 3
    assert top["비율"] == 60.0


def test_analyze_my_category_rank():
    result = analyze(SHOPS, my_category="호프/맥주")
    assert result["my_count"] == 1
    assert result["my_rank"] in (2, 3)  # 카페와 동률(1개)


def test_analyze_empty_shops_no_keyerror():
    """Day 7에서 고친 버그의 회귀 테스트: 반경 내 0곳이어도 KeyError가 없어야 한다."""
    result = analyze([])
    assert result["total"] == 0
    assert len(result["by_category"]) == 0
    assert result["my_rank"] is None

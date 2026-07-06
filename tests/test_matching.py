"""matching/ — 상호 정규화·명부 매칭 (30m 블로킹, 보수적 임계)"""

from core import schema
from matching.matcher import match_rosters, pair_score
from matching.normalize import normalize_name
from tests.conftest import make_roster


# ── 정규화 ───────────────────────────────────────────────────────────────────
def test_normalize_strips_corp_paren_branch():
    assert normalize_name("주식회사 하프하우스") == "하프하우스"
    assert normalize_name("김밥천국(2호점)") == "김밥천국"
    assert normalize_name("등촌샤브칼국수 강남역점") == "등촌샤브칼국수강남"
    assert normalize_name("(주)써브웨이 강남역점") == "써브웨이강남"


def test_normalize_keeps_short_results_raw():
    """제거 후 2글자 미만이면 과제거 — 원형 유지 (오병합 방지)."""
    assert normalize_name("꼬점") == "꼬점"  # '점' 제거 시 1글자 — 원형 유지


def test_normalize_preserves_inner_jeom():
    assert normalize_name("역전주점") == "역전주"  # 말미 '점'만 제거
    assert normalize_name("점봉산막국수") == "점봉산막국수"  # 중간 '점' 보존


# ── 매칭 ─────────────────────────────────────────────────────────────────────
def test_pair_score_same_name_nearby_is_high():
    score, name_sim = pair_score("홍수", "홍수", distance_m=5)
    assert name_sim == 1.0 and score > 0.95


def test_match_rosters_conservative():
    left = make_roster(
        [
            {schema.NAME: "홍수", schema.LAT: 37.4979, schema.LON: 127.0276},
            {schema.NAME: "김밥천국 강남점", schema.LAT: 37.4981, schema.LON: 127.0278},
            {schema.NAME: "완전다른집", schema.LAT: 37.4983, schema.LON: 127.0280},
        ]
    )
    right = make_roster(
        [
            # 같은 업소, 좌표 10m 이내 오차 + 표기 차이
            {schema.NAME: "홍수", schema.LAT: 37.49795, schema.LON: 127.02765},
            {schema.NAME: "김밥천국(강남점)", schema.LAT: 37.49812, schema.LON: 127.02781},
            # 이름이 전혀 다른 이웃 — 매칭되면 안 됨
            {schema.NAME: "옆집치킨", schema.LAT: 37.4983, schema.LON: 127.0280},
        ]
    )
    matches = match_rosters(left, right)
    matched_names = {(left.loc[m.left_idx, schema.NAME], right.loc[m.right_idx, schema.NAME]) for m in matches}
    assert ("홍수", "홍수") in matched_names
    assert ("김밥천국 강남점", "김밥천국(강남점)") in matched_names
    assert all("완전다른집" != l for l, _ in matched_names)  # 미병합으로 남아야 함
    # 1:1 보장
    assert len({m.left_idx for m in matches}) == len(matches)
    assert len({m.right_idx for m in matches}) == len(matches)


def test_match_rosters_far_pair_excluded():
    """이름이 같아도 60m 밖이면 후보에서 제외 — 동명 다른 지점."""
    left = make_roster([{schema.NAME: "홍수", schema.LAT: 37.4979, schema.LON: 127.0276}])
    right = make_roster([{schema.NAME: "홍수", schema.LAT: 37.4990, schema.LON: 127.0290}])  # ≈170m
    assert match_rosters(left, right) == []

"""ui.chat_context 순수 함수 테스트 — 화면 데이터 직렬화·절단 표기.

챗봇 API 호출(ui.chatbot)은 테스트 대상이 아니다(Gemini 실호출). 여기서는
컨텍스트 문자열이 화면 데이터를 빠짐없이·정확히 담고, 상한 초과 시 절단을 명시하는지만
검증한다(CLAUDE.md: 조용한 절단 금지).
"""

from types import SimpleNamespace

import pandas as pd

from core import schema
from signals.base import IndicatorResult
from ui import chat_context

from tests.conftest import make_roster


def _display(roster: pd.DataFrame, statuses: list[str]) -> pd.DataFrame:
    df = roster.copy()
    df["상태"] = statuses
    return df


# ── 지도 ────────────────────────────────────────────────────────────────────
def test_map_context_lists_shops_with_area_and_address():
    roster = make_roster([
        {schema.NAME: "호프하우스", schema.CAT_S: "호프/통닭", schema.AREA_M2: 99.2,
         schema.ADDR_ROAD: "서울 강남구 테헤란로 10"},
        {schema.NAME: "국밥집", schema.CAT_S: "한식", schema.AREA_M2: 33.0},
    ])
    ctx = chat_context.map_context(_display(roster, ["신규", "영업"]), 127.0, 37.5, 300, only_core=False)
    assert "🗺️ 지도" in ctx
    assert "호프하우스" in ctx and "국밥집" in ctx
    assert "서울 강남구 테헤란로 10" in ctx
    assert "㎡" in ctx and "평" in ctx  # 면적 평 환산 병기
    assert "신규 1" in ctx  # 요약 카운트


def test_map_context_none_display_is_graceful():
    ctx = chat_context.map_context(None, 127.0, 37.5, 300, only_core=True)
    assert "수집되지 않아" in ctx
    assert "주류 중심" in ctx  # only_core 반영


def test_map_context_truncates_and_says_so():
    rows = [{schema.NAME: f"업소{i}"} for i in range(chat_context.MAP_MAX_ROWS + 5)]
    roster = make_roster(rows)
    display = _display(roster, ["영업"] * len(roster))
    ctx = chat_context.map_context(display, 127.0, 37.5, 400, only_core=False)
    assert f"상위 {chat_context.MAP_MAX_ROWS}곳만" in ctx
    # 마지막(절단된) 업소는 표에 없어야 한다
    assert f"업소{chat_context.MAP_MAX_ROWS + 4}" not in ctx


# ── 방문 우선순위 ─────────────────────────────────────────────────────────────
def test_ranking_context_has_scorer_badges_and_phase():
    top = pd.DataFrame({
        "순위": [1, 2],
        schema.NAME: ["지안식당", "샐러링"],
        schema.CAT_S: ["한식", "카페"],
        "점수": [0.98, 0.91],
        schema.ADDR_ROAD: ["강남대로 1", "강남대로 2"],
        "근거배지목록": [["🎯 기대치의 3.2배", "블로그 100건"], ["🌱 개업 98일차"]],
    })
    scorer = SimpleNamespace(label="숨은 맛집", description="입소문 강한 집")
    ctx = chat_context.ranking_context(top, scorer, {"국면": "📈 확장"}, n_excluded=23, radius=400)
    assert "숨은 맛집" in ctx and "입소문 강한 집" in ctx
    assert "지안식당" in ctx and "강남대로 1" in ctx
    assert "기대치의 3.2배 / 블로그 100건" in ctx  # 배지 join
    assert "📈 확장" in ctx
    assert "23곳" in ctx  # 제외 안내
    assert "글 원문" in ctx  # 미수집 가드 문구


# ── 구역 동향 ──────────────────────────────────────────────────────────────────
def test_outlook_context_has_phase_indicators_and_recent(gangnam_roster):
    geo = gangnam_roster.dropna(subset=[schema.LAT, schema.LON])
    results = {
        "net_momentum": IndicatorResult(
            current=0.12, previous=0.05, series=None, percentile=80.0,
            fact="최근 12개월 개업 3·폐업 1 — 활성업소 대비 순증 +12%",
        )
    }
    ctx = chat_context.outlook_context(geo, geo, results, radius=300, eff_radius=800, widened=True)
    assert "📈 구역 동향" in ctx
    assert "담당구역으로 확대" in ctx  # widened 반영
    assert "순증 모멘텀" in ctx  # 레지스트리 label
    assert "활성업소 대비 순증 +12%" in ctx  # fact 인용
    assert "백분위 80%" in ctx


def test_outlook_context_handles_empty_indicators(gangnam_roster):
    geo = gangnam_roster.dropna(subset=[schema.LAT, schema.LON])
    ctx = chat_context.outlook_context(geo, geo, {}, radius=300, eff_radius=300, widened=False)
    assert "지표 없음" in ctx
    assert "기준 반경 300m" in ctx

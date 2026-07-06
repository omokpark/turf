"""turf — 얇은 진입점 (Phase 3 분해 후)

구성 요소는 전부 모듈로 분리되어 있다:
- 세션 상태·UI 상수: ui/state.py
- 사이드바(검색·필터): ui/sidebar.py
- 지도 뷰·상호작용 JS: ui/map_view.py + ui/map_interactions.js (JS↔파이썬 채널은 ui/channels.py)
- 페이지: ui/pages/{explore,outlook,changes,ranking}.py
- 데이터: datasources/semas.py(Provider) + datasources/cache.py(격자 parquet 캐시)

동작 원칙(Day 8 확정): '조회하기' 버튼 없음 — 위치가 정해지면 여유 반경으로 1회만
프리페치하고, 반경 슬라이더·업종 필터는 API 호출 없이 로컬 필터로 즉시 반영된다.
"""

import streamlit as st

import datasources.semas  # noqa: F401 — import = Provider 레지스트리 등록
from analyzer.terrain import analyze
from core.area import Area, FETCH_RADIUS_M, filter_radius
from datasources import cache
from datasources.base import get_provider
from ui import sidebar, state
from ui.pages.changes import render_changes
from ui.pages.explore import render_map_tab, render_stats_tab
from ui.pages.outlook import render_outlook
from ui.pages.ranking import render_ranking

st.set_page_config(page_title="turf", layout="wide")

radius = state.init_session()

# ── 데이터: 격자 스냅 중심 프리페치(여유 반경) → 정확한 중심·반경 로컬 필터 → 집계 ──
# 사이드바의 업종 필터가 분석 결과(업종 목록·개수)를 필요로 하므로 데이터를 먼저 만든다.
try:
    with st.spinner("상권 데이터 불러오는 중..."):
        roster = cache.fetch_cached(
            get_provider("semas"),
            Area(cx=st.session_state.cx, cy=st.session_state.cy, radius=FETCH_RADIUS_M),
        )
except Exception as e:
    st.error(f"상가 데이터를 불러오지 못했습니다: {e}")
    st.stop()

analysis = analyze(filter_radius(roster, Area(cx=st.session_state.cx, cy=st.session_state.cy, radius=radius)))
state.notify_reanalysis(analysis["total"], radius)

selected_categories = sidebar.render_sidebar(analysis)
category_colors = {
    cat: state.CATEGORY_PALETTE[i % len(state.CATEGORY_PALETTE)] for i, cat in enumerate(selected_categories)
}

tab_map, tab_stats, tab_outlook, tab_changes, tab_ranking = st.tabs(
    ["🗺️ 지도", "📊 업종 구성", "📈 구역 아웃룩", "🔄 변화", "🎯 방문 우선순위"]
)

with tab_outlook:
    render_outlook(st.session_state.cx, st.session_state.cy)

with tab_changes:
    render_changes(st.session_state.cx, st.session_state.cy, radius)

with tab_ranking:
    render_ranking(st.session_state.cx, st.session_state.cy, radius)

with tab_map:
    render_map_tab(radius, analysis, selected_categories, category_colors)

with tab_stats:
    render_stats_tab(radius, analysis, selected_categories, category_colors)

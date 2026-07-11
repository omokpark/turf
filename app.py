"""Sales Radar — 얇은 진입점 (영업사원 관점 3화면 구조)

전 화면이 인허가(MOI) 데이터 위에서 돈다 — 담당구역(수집된 자치단체) 안에서
"뭐가 새로 생겼고 뭐가 빠졌나 / 이 구역이 뜨나 지나 / 어디부터 방문할까"를 답한다.

화면 전환은 st.tabs가 아니라 segmented_control + 분기다 — st.tabs는 보이지 않는
탭의 with 블록도 매 rerun 실행하므로, 지도만 보는 사용자도 방문 우선순위의
Naver·Places 파이프라인 비용을 치르게 된다(Day 14에 교체). 선택된 화면만 실행한다.

- 세션 상태·UI 상수: ui/state.py
- 사이드바(검색·초기화): ui/sidebar.py
- 지도 뷰·상호작용 JS: ui/map_view.py + ui/map_interactions.js (채널 해석: ui/channels.py)
- 페이지: ui/pages/{explore(지도), outlook(구역 동향), ranking(방문 우선순위)}.py
- 데이터: datasources/moi_store.py (수집된 인허가 parquet 파티션) — 로더는 ui/data.py
"""

import streamlit as st

from core import schema
from core.area import Area, filter_radius
from ui import data, sidebar, state, theme
from ui.pages.explore import render_map_tab
from ui.pages.outlook import render_outlook
from ui.pages.ranking import render_ranking

st.set_page_config(page_title="Sales Radar", layout="wide")
theme.inject_base_styles()

radius = state.init_session()
roster = data.load_roster()

# 재분석 완료 토스트 (지도 리마운트 깜빡임을 오류로 오인하지 않도록)
near_n = 0
if len(roster) > 0:
    near = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]),
                         Area(cx=st.session_state.cx, cy=st.session_state.cy, radius=radius))
    near_n = int(near[schema.IS_OPEN].sum())  # 영업중만 — 토스트 수치의 의미를 명확히
state.notify_reanalysis(near_n, radius)

sidebar.render_sidebar()

PAGE_MAP = "🗺️ 지도"
PAGE_OUTLOOK = "📈 구역 동향"
PAGE_RANKING = "🎯 방문 우선순위"

page = st.segmented_control(
    "화면",
    [PAGE_MAP, PAGE_OUTLOOK, PAGE_RANKING],
    default=PAGE_MAP,
    key="active_page",
    label_visibility="collapsed",
)

# segmented_control은 선택 항목을 다시 누르면 해제(None)될 수 있다 — 지도로 폴백
if page == PAGE_OUTLOOK:
    render_outlook(st.session_state.cx, st.session_state.cy, radius)
elif page == PAGE_RANKING:
    render_ranking(st.session_state.cx, st.session_state.cy, radius)
else:
    render_map_tab(st.session_state.cx, st.session_state.cy, radius)

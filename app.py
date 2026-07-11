"""Sales Radar — 얇은 진입점 (영업사원 관점 3탭 구조)

전 화면이 인허가(MOI) 데이터 위에서 돈다 — 담당구역(수집된 자치단체) 안에서
"뭐가 새로 생겼고 뭐가 빠졌나 / 이 구역이 뜨나 지나 / 어디부터 방문할까"를 답한다.

- 세션 상태·UI 상수: ui/state.py
- 사이드바(검색·초기화): ui/sidebar.py
- 지도 뷰·상호작용 JS: ui/map_view.py + ui/map_interactions.js (채널 해석: ui/channels.py)
- 페이지: ui/pages/{explore(지도), outlook(구역 동향), ranking(방문 우선순위)}.py
- 데이터: datasources/moi_store.py (수집된 인허가 parquet 파티션)
"""

import pandas as pd
import streamlit as st

from core import schema
from core.area import Area, filter_radius
from datasources import moi_store
from ui import sidebar, state, theme
from ui.pages.explore import render_map_tab
from ui.pages.outlook import render_outlook
from ui.pages.ranking import render_ranking

st.set_page_config(page_title="Sales Radar", layout="wide")
theme.inject_base_styles()

radius = state.init_session()


@st.cache_data(ttl=600, show_spinner=False)
def _load_roster(cache_key: tuple) -> pd.DataFrame:
    return moi_store.load_roster()


roster = _load_roster(moi_store.cache_token())

# 재분석 완료 토스트 (지도 리마운트 깜빡임을 오류로 오인하지 않도록)
near_n = 0
if len(roster) > 0:
    near = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]),
                         Area(cx=st.session_state.cx, cy=st.session_state.cy, radius=radius))
    near_n = int(near[schema.IS_OPEN].sum())  # 영업중만 — 토스트 수치의 의미를 명확히
state.notify_reanalysis(near_n, radius)

sidebar.render_sidebar()

tab_map, tab_outlook, tab_ranking = st.tabs(["🗺️ 지도", "📈 구역 동향", "🎯 방문 우선순위"])

with tab_map:
    render_map_tab(roster, st.session_state.cx, st.session_state.cy, radius)

with tab_outlook:
    render_outlook(st.session_state.cx, st.session_state.cy, radius)

with tab_ranking:
    render_ranking(st.session_state.cx, st.session_state.cy, radius)

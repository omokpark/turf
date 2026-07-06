"""JS↔파이썬 채널의 파이썬 쪽 끝 — st_folium 반환값 해석의 단일 장소

JS 쪽 끝은 ui/map_interactions.js. 채널 2개:

① 반경 (last_object_clicked_tooltip): JS가 엣지 리사이즈를 끝내면 핀 툴팁에
   "TURF_RADIUS:값:논스"를 심고 핀 click을 합성한다 — streamlit-folium이 클릭된
   객체의 툴팁 텍스트를 그대로 돌려주는 것을 이용한 우회 채널. 논스로 같은 메시지의
   중복 적용을 막고, 슬라이더 위젯은 이미 그려진 뒤라 pending_radius에 담아 rerun.

② 중심 (last_clicked): 원/핀 드래그의 합성 click 또는 실제 지도 클릭. 마커 클릭
   (팝업 열기)은 last_object_clicked로 함께 들어오므로 중심 이동으로 취급하지 않고,
   st_folium이 rerun마다 같은 last_clicked를 반환하므로 처리한 클릭은 세션에 기록해
   중복 처리를 막는다.
"""

import streamlit as st

from ui.state import move_to


def apply_radius_message(map_data: dict) -> None:
    tooltip_msg = map_data.get("last_object_clicked_tooltip") or ""
    if not tooltip_msg.startswith("TURF_RADIUS:"):
        return
    parts = tooltip_msg.split(":")
    if len(parts) == 3 and parts[1].isdigit() and parts[2] != st.session_state.get("processed_radius_nonce"):
        st.session_state.processed_radius_nonce = parts[2]
        st.session_state.pending_radius = int(parts[1])
        st.rerun()


def apply_center_click(map_data: dict) -> None:
    clicked = map_data.get("last_clicked")
    if clicked and clicked != map_data.get("last_object_clicked"):
        click_key = (round(clicked["lat"], 6), round(clicked["lng"], 6))
        if st.session_state.get("processed_click") != click_key:
            st.session_state.processed_click = click_key
            move_to(clicked["lng"], clicked["lat"])
            st.rerun()

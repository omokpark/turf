"""세션 상태와 UI 공용 상수의 단일 출처

세션 키:
- cx, cy: 분석 중심 (확정 좌표)
- radius_slider: 반경 위젯 값 — 반경 상태의 단일 소스
- pending_radius: 엣지 리사이즈로 들어온 새 반경. 커밋은 st_folium 반환값 처리
  (ui/channels.py)에서 발견되는데 그 시점엔 슬라이더 위젯이 이미 그려져 있어 값을
  직접 못 바꾼다 — 여기 담아 rerun 후 init_session()에서 반영한다.
- moved_address / last_analysis_key: 재분석 토스트용
- address_candidates / processed_click / processed_radius_nonce: 검색·채널 중복 방지
"""

import streamlit as st

from core.area import DEFAULT_RADIUS_M, MAX_RADIUS_M, MIN_RADIUS_M

GANGNAM_STATION = (127.027619, 37.497925)  # (cx, cy)

CENTER_COLOR = "#3388ff"  # 반경 원 색상
NEUTRAL_COLOR = "#9aa5a0"
CATEGORY_PALETTE = ["#c0392b", "#2f6e5b", "#b07d1f", "#5b4b8a", "#1f6f91", "#8a4b6b", "#4b8a4f", "#8a6b4b"]
CLUSTER_THRESHOLD = 40
MAX_CANDIDATES = 5

CROSSHAIR_HTML = """
<svg width="22" height="22" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="11" y1="0" x2="11" y2="22" stroke="#c0392b" stroke-width="2"/>
  <line x1="0" y1="11" x2="22" y2="11" stroke="#c0392b" stroke-width="2"/>
  <circle cx="11" cy="11" r="3.5" fill="white" stroke="#c0392b" stroke-width="2"/>
</svg>
"""


def init_session() -> int:
    """세션 기본값을 채우고 현재 반경을 돌려준다. 매 rerun 최상단에서 1회 호출."""
    if "cx" not in st.session_state:
        st.session_state.cx, st.session_state.cy = GANGNAM_STATION
    if "radius_slider" not in st.session_state:
        st.session_state.radius_slider = DEFAULT_RADIUS_M
    if "pending_radius" in st.session_state:
        st.session_state.radius_slider = st.session_state.pop("pending_radius")
    st.session_state.radius_slider = min(MAX_RADIUS_M, max(MIN_RADIUS_M, st.session_state.radius_slider))
    return st.session_state.radius_slider


def move_to(cx: float, cy: float) -> None:
    st.session_state.cx = cx
    st.session_state.cy = cy


def notify_reanalysis(total: int, radius: int) -> None:
    """조건 변경(원 드래그·지도 클릭·반경·주소 검색)으로 재분석되면 완료 토스트를 띄운다.

    지도가 다시 그려지며 잠깐 깜빡이는 것이 오류로 오인되지 않게 하기 위함. 첫 로드는 조용히.
    """
    moved_address = st.session_state.pop("moved_address", None)
    analysis_key = (round(st.session_state.cx, 6), round(st.session_state.cy, 6), radius)
    if st.session_state.get("last_analysis_key") != analysis_key:
        if "last_analysis_key" in st.session_state:
            where = f"'{moved_address}' 기준 " if moved_address else ""
            st.toast(f"{where}재분석 완료 — 반경 {radius}m 내 영업중 업소 {total}곳", icon="📍")
        st.session_state.last_analysis_key = analysis_key

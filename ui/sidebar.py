"""사이드바 — 검색·필터 패널. 정확한 중심·반경 조작은 본문 지도에서."""

import streamlit as st

from collector.geocoder import geocode_address, search_places
from core.area import DEFAULT_RADIUS_M
from datasources import favorites_store
from ui.state import GANGNAM_STATION, MAX_CANDIDATES, move_to


def _dedupe_by_district(candidates: list[dict]) -> list[dict]:
    """주소의 '시/도 시/군/구'가 같은 후보는 먼저 나온 것 하나만 남긴다."""
    seen = set()
    deduped = []
    for c in candidates:
        parts = (c["address"] or c["title"]).split()
        key = " ".join(parts[:2]) if len(parts) >= 2 else (c["address"] or c["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def _render_address_search() -> None:
    st.markdown("**📍 위치 — 주소/장소 검색** (예: 역삼동, 삼성역)")
    with st.form("address_form", clear_on_submit=False):
        address = st.text_input("주소", label_visibility="collapsed")
        submitted = st.form_submit_button("🔍 검색")
    if submitted and address:
        st.session_state.address_candidates = None
        try:
            address_match = geocode_address(address)
            place_matches = search_places(address)
        except RuntimeError as e:
            st.error(str(e))
        else:
            # 주소 API는 퍼지 매칭을 하므로(예: '삼성역' -> 경산시 '삼성역길') 결과가 있어도
            # 바로 이동하지 않고, 장소명 검색 결과와 합쳐서 항상 사용자 확인을 거친다.
            # 같은 시/군/구 안의 중복 후보는 하나로 줄인다.
            candidates = _dedupe_by_district(([address_match] if address_match else []) + place_matches)
            # 이름이 검색어와 정확히 일치하는 후보(예: '삼성역' 역 자체)를 퍼지 매칭 주소보다 앞에
            candidates.sort(key=lambda c: c["title"] != address)
            candidates = candidates[:MAX_CANDIDATES]
            if len(candidates) == 1:
                # 후보가 하나뿐이면 모호하지 않으므로 바로 이동한다.
                chosen = candidates[0]
                move_to(chosen["cx"], chosen["cy"])
                st.session_state.moved_address = chosen["title"]
                st.rerun()
            elif candidates:
                st.session_state.address_candidates = candidates
            else:
                st.warning("주소 또는 장소를 찾을 수 없습니다.")

    if st.session_state.get("address_candidates"):
        st.caption("🔽 검색 결과 — 원하는 위치를 누르면 바로 이동합니다")
        for i, c in enumerate(st.session_state.address_candidates):
            label = f"{c['title']} — {c['address']}" if c["address"] and c["address"] != c["title"] else c["title"]
            if st.button(label, key=f"candidate_{i}", use_container_width=True):
                move_to(c["cx"], c["cy"])
                st.session_state.moved_address = c["title"]
                st.session_state.address_candidates = None
                st.rerun()

    st.caption("정확한 위치·반경은 지도에서 — 파란 원을 끌면 중심이, 원 가장자리를 끌면 반경이 바뀝니다.")


def _render_favorites() -> None:
    """담당구역 즐겨찾기 — 이름은 자유 텍스트라 우편번호·행정동 등 회사가 통보하는
    어떤 단위든 라벨로 쓸 수 있다(실제 위치는 저장 시점의 지도 중심을 그대로 씀)."""
    st.markdown("**⭐ 담당구역 즐겨찾기**")
    favorites = favorites_store.list_favorites()
    if not favorites:
        st.caption("저장된 위치가 없습니다.")
    for f in favorites:
        go_col, del_col = st.columns([4, 1])
        with go_col:
            if st.button(f["이름"], key=f"fav_go_{f['이름']}", use_container_width=True):
                move_to(f["cx"], f["cy"])
                st.rerun()
        with del_col:
            if st.button("✕", key=f"fav_del_{f['이름']}", use_container_width=True):
                favorites_store.remove_favorite(f["이름"])
                st.rerun()

    with st.form("favorite_form", clear_on_submit=True):
        name = st.text_input(
            "이름", label_visibility="collapsed", placeholder="이름 (예: 06018, 역삼1동)"
        )
        submitted = st.form_submit_button("⭐ 현재 위치 저장")
    name = (name or "").strip()
    if submitted and name:
        favorites_store.add_favorite(name, st.session_state.cx, st.session_state.cy)
        st.toast(f"⭐ '{name}' 저장했습니다.")
        st.rerun()


def render_sidebar() -> None:
    """사이드바 — 검색·즐겨찾기·위치 초기화. (업종 필터는 영업사원 관점에서 불필요해
    제거, 지도가 주류 가능 업소를 전부 보여준다.)"""
    with st.sidebar:
        st.title("🍶 Sales Radar")
        _render_address_search()
        st.divider()
        _render_favorites()
        st.divider()
        if st.button("↩️ 초기 위치(강남역)로"):
            move_to(*GANGNAM_STATION)
            st.session_state.radius_slider = DEFAULT_RADIUS_M
            st.rerun()

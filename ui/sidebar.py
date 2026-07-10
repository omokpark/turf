"""사이드바 — 검색·필터 패널. 정확한 중심·반경 조작은 본문 지도에서."""

import streamlit as st

from collector.geocoder import geocode_address, search_places
from core.area import DEFAULT_RADIUS_M
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


def _render_category_filter(analysis: dict) -> list[str]:
    from core import schema

    st.markdown("**🍽️ 업종 필터** — 선택한 업종만 지도 마커·업소 목록에 표시 (비우면 전체 집계)")
    if analysis["total"] == 0:
        st.caption("반경 내 음식점이 없어 선택할 업종이 없습니다.")
        return []

    by_category = analysis["by_category"]
    options = by_category[schema.CAT_S].tolist()  # 이미 개수 많은 순 정렬
    counts = by_category.set_index(schema.CAT_S)["개수"]
    # 위치·반경이 바뀌어 현재 결과에 없는 업종이 필터에 남아 있으면 제거 (multiselect 생성 전에 정리)
    if st.session_state.get("filter_categories"):
        st.session_state.filter_categories = [c for c in st.session_state.filter_categories if c in options]
    return st.multiselect(
        "업종 필터",
        options,
        key="filter_categories",
        format_func=lambda c: f"{c} ({counts[c]}곳)",
        label_visibility="collapsed",
    )


def render_sidebar(analysis: dict) -> list[str]:
    """사이드바 전체를 그리고 선택된 업종 필터를 돌려준다."""
    with st.sidebar:
        st.title("🍶 Sales Radar")
        _render_address_search()
        selected_categories = _render_category_filter(analysis)
        if st.button("↩️ 초기 위치(강남역)로"):
            move_to(*GANGNAM_STATION)
            st.session_state.radius_slider = DEFAULT_RADIUS_M
            st.rerun()
    return selected_categories

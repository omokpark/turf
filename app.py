"""Streamlit + folium 지도 UI (Day 3~8)

Day 8 구조:
- '조회하기' 버튼 없음. 위치가 정해지면 최대 반경(500m)으로 1회만 프리페치하고,
  반경 슬라이더·업종 필터는 API 호출 없이 로컬 필터로 즉시 반영된다.
- 반경은 도보 상권 기준 최소 100 / 기본 300 / 최대 500m, 도보 시간 병기.
- 주소 검색 후보는 드롭다운 대신 버튼으로 나열해 클릭 즉시 이동.
- 지도는 표시 전용. 중심 미세조정은 "지도 클릭 = 중심 이동".
- 결과는 st.tabs 2개: ① 지도(밀집도 히트맵 + 선택 업종 마커) ② 업종 구성(차트·목록).
"""

import html
import math
import os

import altair as alt
import folium
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

from analyzer.terrain import analyze
from collector.geocoder import geocode_address, search_places
from collector.shop_fetcher import fetch_shops
from presenter.report import generate_report

GANGNAM_STATION = (127.027619, 37.497925)  # (cx, cy)
CENTER_COLOR = "#3388ff"  # 반경 원 색상
NEUTRAL_COLOR = "#9aa5a0"
CATEGORY_PALETTE = ["#c0392b", "#2f6e5b", "#b07d1f", "#5b4b8a", "#1f6f91", "#8a4b6b", "#4b8a4f", "#8a6b4b"]
CLUSTER_THRESHOLD = 40
MIN_RADIUS_M = 100  # 한 블록 — 초밀집 지역용
DEFAULT_RADIUS_M = 300  # 도보 5분 = 점심 상권의 실질 한계선
MAX_RADIUS_M = 400  # 도보 상권 상한
FETCH_RADIUS_M = MAX_RADIUS_M + 50  # 프리페치 반경 — 격자 스냅 오차(≤21m)를 여유 있게 흡수
FETCH_GRID_M = 30  # 프리페치 캐시 키용 격자. 가까운 지점을 다시 클릭해도 같은 셀이면 재조회 없음
MAX_CANDIDATES = 5
WALK_SPEED_M_PER_MIN = 70

st.set_page_config(page_title="turf", layout="wide")


@st.cache_data(ttl=300, show_spinner=False)
def _load_area_shops(cx: float, cy: float) -> list[dict]:
    """격자 스냅된 중심 기준으로 여유 반경만큼 조회해 둔다. 반경 조절·미세 이동은 로컬 필터로 처리."""
    return fetch_shops(cx, cy, FETCH_RADIUS_M)


def _snap_to_grid(cx: float, cy: float) -> tuple[float, float]:
    """프리페치 캐시 키용으로 좌표를 격자 단위로 반올림한다."""
    lat_step = FETCH_GRID_M / 111_320
    lon_step = FETCH_GRID_M / (111_320 * math.cos(math.radians(cy)))
    return round(cx / lon_step) * lon_step, round(cy / lat_step) * lat_step


CROSSHAIR_HTML = """
<svg width="22" height="22" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">
  <line x1="11" y1="0" x2="11" y2="22" stroke="#c0392b" stroke-width="2"/>
  <line x1="0" y1="11" x2="22" y2="11" stroke="#c0392b" stroke-width="2"/>
  <circle cx="11" cy="11" r="3.5" fill="white" stroke="#c0392b" stroke-width="2"/>
</svg>
"""


def _within_radius(shops: list[dict], cx: float, cy: float, radius: int) -> list[dict]:
    """중심에서 radius(m) 이내 업소만 남긴다. 500m 스케일에선 등장방형 근사로 충분하다."""
    meters_per_deg_lon = 111_320 * math.cos(math.radians(cy))
    result = []
    for s in shops:
        dx = (s["경도"] - cx) * meters_per_deg_lon
        dy = (s["위도"] - cy) * 111_320
        if dx * dx + dy * dy <= radius * radius:
            result.append(s)
    return result


def _walk_minutes(radius: int) -> int:
    return max(1, round(radius / WALK_SPEED_M_PER_MIN))


def _zoom_for_radius(radius: int) -> int:
    """반경 원(지름)이 지도 높이 560px의 절반~3/4을 채우는 줌.

    위도 37.5° 기준 담기는 세로 폭: 줌 16 ≈ 1,060m, 줌 17 ≈ 530m.
    fit_bounds는 요구 박스가 조금만 넘쳐도 줌을 한 단계 내려버려(예: 1,100m 박스 → 줌 15)
    화면이 비어 보이므로 쓰지 않고 직접 지정한다.
    """
    return 17 if radius <= 200 else 16


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


if "cx" not in st.session_state:
    st.session_state.cx, st.session_state.cy = GANGNAM_STATION
if "radius_slider" not in st.session_state:
    st.session_state.radius_slider = DEFAULT_RADIUS_M
# 엣지 리사이즈 커밋은 st_folium 반환값 처리(스크립트 하단)에서 발견되는데, 그 시점엔 반경
# 슬라이더 위젯이 이미 그려져 있어 값을 직접 못 바꾼다 — pending에 담아 rerun 후 여기서 반영.
if "pending_radius" in st.session_state:
    st.session_state.radius_slider = st.session_state.pop("pending_radius")
st.session_state.radius_slider = min(MAX_RADIUS_M, max(MIN_RADIUS_M, st.session_state.radius_slider))
radius = st.session_state.radius_slider


def move_to(cx: float, cy: float) -> None:
    st.session_state.cx = cx
    st.session_state.cy = cy


# ── 데이터: 격자 스냅 중심 프리페치(450m) → 정확한 중심·반경 로컬 필터 → 집계 ──
# 사이드바의 업종 필터가 분석 결과(업종 목록·개수)를 필요로 하므로 데이터를 먼저 만든다.
try:
    with st.spinner("상권 데이터 불러오는 중..."):
        snapped_cx, snapped_cy = _snap_to_grid(st.session_state.cx, st.session_state.cy)
        area_shops = _load_area_shops(snapped_cx, snapped_cy)
except Exception as e:
    st.error(f"상가 데이터를 불러오지 못했습니다: {e}")
    st.stop()

analysis = analyze(_within_radius(area_shops, st.session_state.cx, st.session_state.cy, radius))
by_category = analysis["by_category"]

# 원 드래그·지도 클릭·반경 조절·주소 검색으로 조건이 바뀌면 지도가 다시 그려지며 잠깐
# 깜빡이는데, 이것이 오류로 오인되지 않도록 재분석 완료를 토스트로 명확히 알린다.
moved_address = st.session_state.pop("moved_address", None)
analysis_key = (round(st.session_state.cx, 6), round(st.session_state.cy, 6), radius)
if st.session_state.get("last_analysis_key") != analysis_key:
    if "last_analysis_key" in st.session_state:  # 첫 로드는 조용히
        where = f"'{moved_address}' 기준 " if moved_address else ""
        st.toast(f"{where}재분석 완료 — 반경 {radius}m 내 음식점 {analysis['total']}곳", icon="📍")
    st.session_state.last_analysis_key = analysis_key

# ── 사이드바: 검색·필터 패널. 정확한 중심·반경 조작은 본문 지도에서 ──────────
with st.sidebar:
    st.title("공공API기반의 상권분석")

    st.markdown("**① 위치 — 주소/장소 검색** (예: 역삼동, 삼성역)")
    with st.form("address_form", clear_on_submit=False):
        address = st.text_input("주소", label_visibility="collapsed")
        submitted = st.form_submit_button("검색")
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
        st.caption("검색 결과 — 원하는 위치를 누르면 바로 이동합니다")
        for i, c in enumerate(st.session_state.address_candidates):
            label = f"{c['title']} — {c['address']}" if c["address"] and c["address"] != c["title"] else c["title"]
            if st.button(label, key=f"candidate_{i}", use_container_width=True):
                move_to(c["cx"], c["cy"])
                st.session_state.moved_address = c["title"]
                st.session_state.address_candidates = None
                st.rerun()

    st.caption("정확한 위치·반경은 지도에서 — 파란 원을 끌면 중심이, 원 가장자리를 끌면 반경이 바뀝니다.")

    st.markdown("**② 업종 필터** — 선택한 업종만 지도 마커·업소 목록에 표시 (비우면 전체 집계)")
    selected_categories: list[str] = []
    if analysis["total"] > 0:
        options = by_category["상권업종소분류명"].tolist()  # 이미 개수 많은 순 정렬
        counts = by_category.set_index("상권업종소분류명")["개수"]
        # 위치·반경이 바뀌어 현재 결과에 없는 업종이 필터에 남아 있으면 제거 (multiselect 생성 전에 정리)
        if st.session_state.get("filter_categories"):
            st.session_state.filter_categories = [c for c in st.session_state.filter_categories if c in options]
        selected_categories = st.multiselect(
            "업종 필터",
            options,
            key="filter_categories",
            format_func=lambda c: f"{c} ({counts[c]}곳)",
            label_visibility="collapsed",
        )
    else:
        st.caption("반경 내 음식점이 없어 선택할 업종이 없습니다.")

    if st.button("초기 위치(강남역)로"):
        move_to(*GANGNAM_STATION)
        st.session_state.radius_slider = DEFAULT_RADIUS_M
        st.rerun()

category_colors = {cat: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, cat in enumerate(selected_categories)}

tab_map, tab_stats = st.tabs(["🗺️ 지도", "📊 업종 구성"])

# ── 탭 1: 지도 — 밀집도·분포의 직관적 파악 + 중심·반경 조작 ─────────────────
with tab_map:
    # 반경 컨트롤은 피드백(원 크기)이 보이는 지도 바로 위에 둔다. 원 가장자리 드래그와 동일한 값을 공유.
    slider_col, walk_col = st.columns([5, 1])
    with slider_col:
        st.slider(
            "반경 (m)",
            min_value=MIN_RADIUS_M,
            max_value=MAX_RADIUS_M,
            step=50,
            key="radius_slider",
            label_visibility="collapsed",
        )
    walk_col.markdown(f"**{radius}m** · 도보 {_walk_minutes(radius)}분")

    vworld_key = os.getenv("VWORLD_API_KEY")
    m = folium.Map(
        location=[st.session_state.cy, st.session_state.cx],
        zoom_start=_zoom_for_radius(radius),
        tiles=None if vworld_key else "OpenStreetMap",
        scrollWheelZoom=False,
    )

    if vworld_key:
        folium.TileLayer(
            tiles=f"https://api.vworld.kr/req/wmts/1.0.0/{vworld_key}/Base/{{z}}/{{y}}/{{x}}.png",
            attr="VWorld",
            name="VWorld 배경지도",
            overlay=False,
            control=False,
        ).add_to(m)

    # 반경 원과 중심 십자 핀은 지리 좌표에 고정한다 — 지도를 끌거나 줌해도 분석 중심은
    # 그대로이고, 십자 핀을 드래그하거나 지도를 클릭했을 때만 이동한다.
    folium.Circle(
        [st.session_state.cy, st.session_state.cx],
        radius=radius,
        color=CENTER_COLOR,
        weight=2,
        fill=True,
        fill_opacity=0.08,
    ).add_to(m)
    folium.Marker(
        [st.session_state.cy, st.session_state.cx],
        icon=folium.DivIcon(html=CROSSHAIR_HTML, icon_size=(22, 22), icon_anchor=(11, 11)),
        tooltip="끌어서 분석 중심 이동",
        draggable=True,
        z_index_offset=1000,
    ).add_to(m)

    # 원 영역 아무 곳이나 잡고 드래그해서 분석 중심을 옮긴다. 끄는 동안 원+핀이 커서를 따라오고,
    # 놓는 순간 원 중심 좌표로 지도 click 이벤트를 합성해 쏜다 — streamlit-folium은 도형 드래그를
    # 파이썬으로 돌려주지 않지만 지도 click은 last_clicked로 돌려주므로 아래 처리 로직이 그대로 받는다.
    # 드래그 직후 브라우저가 만드는 잔여 click(원 위에서 mouseup)은 캡처 단계에서 한 번 삼켜
    # last_clicked를 덮어쓰지 못하게 한 뒤 합성 click을 보낸다.
    # folium.Element는 지도 JS 초기화보다 먼저 렌더되므로 img onload + 재시도 패턴으로 늦게 실행한다.
    m.get_root().html.add_child(
        folium.Element(
            """
        <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
             style="display:none" onload="
            (function() {
                function turfInitDrag() {
                    if (typeof map_div === 'undefined') { setTimeout(turfInitDrag, 50); return; }
                    var pin = null, circle = null;
                    map_div.eachLayer(function(l) {
                        if (l instanceof L.Marker && l.options.draggable) { pin = l; }
                        if (l instanceof L.Circle && l.getRadius && l.getRadius() >= 50) { circle = l; }
                    });
                    if (!pin || !circle || !circle.getElement()) { setTimeout(turfInitDrag, 50); return; }

                    function commit() {
                        var ll = circle.getLatLng();
                        map_div.fire('click', {
                            latlng: ll,
                            containerPoint: map_div.latLngToContainerPoint(ll),
                            originalEvent: new MouseEvent('click')
                        });
                    }

                    // 십자 핀 자체 드래그 (Leaflet 기본 draggable)
                    pin.on('drag', function(e) { circle.setLatLng(e.target.getLatLng()); });
                    pin.on('dragend', commit);

                    // 원 드래그(내부 = 중심 이동, 가장자리 = 반경 조절). Leaflet 1.9는 지도 팬을
                    // pointerdown에서 시작하므로(Browser.touch=true) 반드시 pointerdown을 path
                    // 요소에서 직접 잡아 전파를 차단해야 지도가 대신 끌리지 않는다.
                    var el = circle.getElement();
                    var EDGE_BAND_PX = 12;
                    var MIN_R = %(min_r)d, MAX_R = %(max_r)d, STEP_R = 50;
                    var dragging = false;

                    function circleRadiusPx() {
                        var c = circle.getLatLng();
                        var east = L.latLng(c.lat, c.lng + circle.getRadius() / (111320 * Math.cos(c.lat * Math.PI / 180)));
                        return map_div.latLngToContainerPoint(east).distanceTo(map_div.latLngToContainerPoint(c));
                    }
                    function zoneOf(ev) {
                        var pt = map_div.mouseEventToContainerPoint(ev);
                        var cpt = map_div.latLngToContainerPoint(circle.getLatLng());
                        var mode = Math.abs(pt.distanceTo(cpt) - circleRadiusPx()) <= EDGE_BAND_PX ? 'resize' : 'move';
                        return { mode: mode, pt: pt, cpt: cpt };
                    }
                    function edgeCursor(pt, cpt) {
                        var a = ((Math.atan2(pt.y - cpt.y, pt.x - cpt.x) * 180 / Math.PI) + 360) %% 180;
                        if (a < 22.5 || a >= 157.5) { return 'ew-resize'; }
                        if (a < 67.5) { return 'nwse-resize'; }
                        if (a < 112.5) { return 'ns-resize'; }
                        return 'nesw-resize';
                    }
                    el.style.cursor = 'grab';
                    el.addEventListener('pointermove', function(me) {
                        if (dragging) { return; }
                        var z = zoneOf(me);
                        el.style.cursor = z.mode === 'resize' ? edgeCursor(z.pt, z.cpt) : 'grab';
                    });
                    var DOWN = window.PointerEvent ? 'pointerdown' : 'mousedown';
                    var MOVE = window.PointerEvent ? 'pointermove' : 'mousemove';
                    var UP = window.PointerEvent ? 'pointerup' : 'mouseup';
                    el.addEventListener(DOWN, function(de) {
                        de.stopPropagation();  // 지도 팬 시작 차단
                        de.preventDefault();
                        dragging = true;
                        var z = zoneOf(de);
                        if (z.mode === 'move') { el.style.cursor = 'grabbing'; }
                        var startMouse = map_div.mouseEventToLatLng(de);
                        var startCenter = circle.getLatLng();
                        var moved = false;
                        function onMove(me) {
                            moved = true;
                            var ll = map_div.mouseEventToLatLng(me);
                            if (z.mode === 'resize') {
                                var r = Math.max(MIN_R, Math.min(MAX_R, startCenter.distanceTo(ll)));
                                circle.setRadius(r);
                            } else {
                                var nc = L.latLng(
                                    startCenter.lat + (ll.lat - startMouse.lat),
                                    startCenter.lng + (ll.lng - startMouse.lng)
                                );
                                circle.setLatLng(nc);
                                pin.setLatLng(nc);
                            }
                        }
                        function onUp() {
                            document.removeEventListener(MOVE, onMove);
                            dragging = false;
                            el.style.cursor = 'grab';
                            if (!moved) { return; }
                            var cont = map_div.getContainer();
                            var swallow = function(ce) {
                                ce.stopPropagation();
                                ce.preventDefault();
                                cont.removeEventListener('click', swallow, true);
                            };
                            cont.addEventListener('click', swallow, true);
                            setTimeout(function() {
                                cont.removeEventListener('click', swallow, true);
                                if (z.mode === 'resize') {
                                    var snapped = Math.max(MIN_R, Math.min(MAX_R, Math.round(circle.getRadius() / STEP_R) * STEP_R));
                                    circle.setRadius(snapped);
                                    // 새 반경은 last_object_clicked_tooltip 채널로 전달한다:
                                    // 핀 툴팁에 메시지를 심고 핀 click을 합성하면 streamlit-folium이
                                    // 클릭된 객체의 툴팁 텍스트를 파이썬으로 돌려준다. 논스로 중복 방지.
                                    pin.setTooltipContent('TURF_RADIUS:' + snapped + ':' + Date.now());
                                    pin.fire('click', { latlng: pin.getLatLng() });
                                } else {
                                    commit();
                                }
                            }, 60);
                        }
                        document.addEventListener(MOVE, onMove);
                        document.addEventListener(UP, onUp, { once: true });
                    });
                }
                turfInitDrag();
            })();
            ">
            """
            % {"min_r": MIN_RADIUS_M, "max_r": MAX_RADIUS_M}
        )
    )

    if analysis["total"] > 0:
        food_df = analysis["food_df"]

        # 전체 음식점 밀집도 히트맵 — 상권의 '뜨거운 정도'를 한눈에
        heat_group = folium.FeatureGroup(name="전체 음식점 밀집도").add_to(m)
        HeatMap(food_df[["위도", "경도"]].values.tolist(), radius=22, blur=18, min_opacity=0.3).add_to(heat_group)

        my_shops = food_df[food_df["상권업종소분류명"].isin(selected_categories)]
        if not my_shops.empty:
            if len(my_shops) > CLUSTER_THRESHOLD:
                layer = MarkerCluster(name="선택 업종", maxClusterRadius=40, disableClusteringAtZoom=18).add_to(m)
            else:
                layer = folium.FeatureGroup(name="선택 업종").add_to(m)
            for _, row in my_shops.iterrows():
                shop_name = html.escape(str(row["상호"]))
                shop_category = html.escape(str(row["상권업종소분류명"]))
                folium.CircleMarker(
                    location=[row["위도"], row["경도"]],
                    radius=6,
                    color=category_colors.get(row["상권업종소분류명"], NEUTRAL_COLOR),
                    fill=True,
                    fill_opacity=0.85,
                    tooltip=folium.Tooltip(row["상호"], permanent=False, direction="top", sticky=False),
                    popup=folium.Popup(f"<b>{shop_name}</b><br>{shop_category}", max_width=220),
                ).add_to(layer)

        folium.LayerControl(collapsed=True).add_to(m)

        if len(selected_categories) > 1:
            legend_rows = "".join(
                f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
                f'<span style="width:10px;height:10px;border-radius:50%;background:{category_colors[c]};'
                f'display:inline-block;"></span><span>{html.escape(c)}</span></div>'
                for c in selected_categories
            )
            m.get_root().html.add_child(
                folium.Element(
                    f"""
                    <div style="position:fixed; bottom:24px; right:12px; z-index:1000;
                                background:rgba(255,255,255,0.9); border:1px solid #ccc; border-radius:6px;
                                padding:8px 10px; font-size:12px; pointer-events:none;">
                    {legend_rows}
                    </div>
                    """
                )
            )

    map_data = st_folium(m, height=560, use_container_width=True, key="main_map")

    st.caption(
        f"중심: 위도 {st.session_state.cy:.5f}, 경도 {st.session_state.cx:.5f} · "
        f"반경 {radius}m (도보 약 {_walk_minutes(radius)}분) — "
        "원 끌기 = 중심 이동 · 원 가장자리 끌기 = 반경 조절 · 원 밖 클릭 = 점프 · 지도 끌기/줌 = 탐색"
    )

    # 엣지 리사이즈 커밋: JS가 핀 툴팁에 심은 TURF_RADIUS 메시지를 tooltip 채널로 수신.
    # 반경 슬라이더 위젯은 이미 그려진 뒤라 여기서 직접 못 바꾸고, pending에 담아 rerun 후 상단에서 반영.
    tooltip_msg = map_data.get("last_object_clicked_tooltip") or ""
    if tooltip_msg.startswith("TURF_RADIUS:"):
        parts = tooltip_msg.split(":")
        if len(parts) == 3 and parts[1].isdigit() and parts[2] != st.session_state.get("processed_radius_nonce"):
            st.session_state.processed_radius_nonce = parts[2]
            st.session_state.pending_radius = int(parts[1])
            st.rerun()

    # 원/핀 드래그(합성 click으로 수신) 또는 지도 클릭 = 분석 중심 이동.
    # 마커 클릭(팝업 열기)은 last_object_clicked로 함께 들어오므로 중심 이동으로 취급하지 않고,
    # st_folium이 rerun마다 같은 last_clicked를 반환하므로 처리한 클릭은 세션에 기록해 중복 처리를 막는다.
    clicked = map_data.get("last_clicked")
    if clicked and clicked != map_data.get("last_object_clicked"):
        click_key = (round(clicked["lat"], 6), round(clicked["lng"], 6))
        if st.session_state.get("processed_click") != click_key:
            st.session_state.processed_click = click_key
            move_to(clicked["lng"], clicked["lat"])
            st.rerun()

# ── 탭 2: 업종 구성 — 스냅샷 집계 ───────────────────────────────────────────
with tab_stats:
    if analysis["total"] == 0:
        st.info("반경 내 음식점이 없습니다. 위치나 반경을 바꿔보세요.")
    else:
        st.caption(
            f"조회 위치: 위도 {st.session_state.cy:.5f}, 경도 {st.session_state.cx:.5f} · "
            f"반경 {radius}m (도보 약 {_walk_minutes(radius)}분)"
        )

        st.metric("총 음식점", f"{analysis['total']}곳")
        for cat in selected_categories:
            match = by_category[by_category["상권업종소분류명"] == cat]
            cols = st.columns(3)
            cols[0].markdown(f"**{cat}**")
            row = match.iloc[0]
            cols[1].metric("개수", f"{int(row['개수'])}곳", f"{match.index[0] + 1}위", delta_color="off")
            cols[2].metric("비중", f"{row['비율']}%", delta_color="off")

        st.markdown("**업종별 개수·비율** (반경 내, 많은 순)")
        chart_df = by_category.copy().reset_index(drop=True)
        chart_df["순위"] = chart_df.index + 1
        chart_df["표시명"] = chart_df["순위"].astype(str) + "위 " + chart_df["상권업종소분류명"]
        chart_df["라벨"] = chart_df["개수"].astype(str) + "곳 (" + chart_df["비율"].astype(str) + "%)"
        # 지도 범례와 같은 색상 매핑을 사용 — 필터로 선택하지 않은 업종은 중립색
        chart_df["색상"] = chart_df["상권업종소분류명"].map(category_colors).fillna(NEUTRAL_COLOR)

        base = alt.Chart(chart_df).encode(
            y=alt.Y(
                "표시명:N",
                sort=alt.EncodingSortField(field="개수", order="descending"),
                title=None,
                axis=alt.Axis(labelLimit=240),
            )
        )
        bars = base.mark_bar().encode(
            x=alt.X("개수:Q", title="개수"),
            color=alt.Color("색상:N", scale=None, legend=None),
            tooltip=[
                alt.Tooltip("상권업종소분류명:N", title="업종"),
                alt.Tooltip("순위:Q", title="순위"),
                alt.Tooltip("개수:Q", title="개수"),
                alt.Tooltip("비율:Q", title="비율(%)"),
            ],
        )
        labels = base.mark_text(align="left", dx=3).encode(x="개수:Q", text="라벨:N")
        chart_height = max(320, 24 * len(chart_df))
        chart = (bars + labels).properties(height=chart_height)

        if chart_height > 480:
            st.caption("전체 업종을 보려면 아래 차트를 스크롤하세요.")
        with st.container(height=480):
            st.altair_chart(chart, use_container_width=True)

        table_df = analysis["food_df"]
        if selected_categories:
            table_df = table_df[table_df["상권업종소분류명"].isin(selected_categories)]
        st.markdown("**업소 목록**" + (" (선택 업종)" if selected_categories else " (전체)"))
        display_table = (
            table_df[["상호", "상권업종소분류명", "도로명주소"]]
            .rename(columns={"상호": "상호명", "상권업종소분류명": "업종", "도로명주소": "주소"})
            .reset_index(drop=True)
        )
        st.dataframe(display_table, use_container_width=True)
        st.download_button(
            "업소 목록 CSV 다운로드",
            display_table.to_csv(index=False).encode("utf-8-sig"),
            file_name="turf_업소목록.csv",
            mime="text/csv",
        )

        report_text = generate_report(analysis, radius, None)
        for cat in selected_categories:
            match = by_category[by_category["상권업종소분류명"] == cat]
            row = match.iloc[0]
            report_text += (
                f"\n★ 내 업종({cat}): {int(row['개수'])}곳, {match.index[0] + 1}위, {row['비율']}% 차지"
            )
        with st.expander("원본 리포트 텍스트"):
            st.text(report_text)

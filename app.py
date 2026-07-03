"""Streamlit + folium 지도 UI (Day 3~6)"""

import html
import math
import os

import altair as alt
import folium
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from analyzer.terrain import analyze
from collector.categories import get_food_categories
from collector.geocoder import geocode_address, search_places
from collector.shop_fetcher import fetch_shops
from presenter.report import generate_report

GANGNAM_STATION = (127.027619, 37.497925)  # (cx, cy)
MY_COLOR = "#c0392b"
CENTER_COLOR = "#3388ff"  # 반경 원 색상
NEUTRAL_COLOR = "#9aa5a0"
CATEGORY_PALETTE = ["#c0392b", "#2f6e5b", "#b07d1f", "#5b4b8a", "#1f6f91", "#8a4b6b", "#4b8a4f", "#8a6b4b"]
CLUSTER_THRESHOLD = 40
PREVIEW_GRID_METERS = 50  # 업종 빈도 미리보기 캐시 키를 이 단위로 스냅
FIT_BOUNDS_RADIUS_M = 600  # 반경 슬라이더 최댓값 기준 고정 — 슬라이더 값과 무관하게 유지해 지도 리마운트 방지

st.set_page_config(page_title="turf", layout="wide")


@st.cache_data(ttl=86400)
def _food_categories() -> list[str]:
    return get_food_categories()


@st.cache_data(ttl=300)
def _fetch_shops_cached(cx: float, cy: float, radius: int) -> list[dict]:
    return fetch_shops(cx, cy, radius)


def _bounds_center(bounds):
    if not bounds:
        return None
    sw, ne = bounds["_southWest"], bounds["_northEast"]
    return ((sw["lat"] + ne["lat"]) / 2, (sw["lng"] + ne["lng"]) / 2)


def _snap_to_grid(lat: float, lon: float, grid_meters: int = PREVIEW_GRID_METERS) -> tuple[float, float]:
    """업종 빈도 미리보기 캐시 키용으로 좌표를 격자 단위로 반올림한다."""
    lat_step = grid_meters / 111_320
    lon_step = grid_meters / (111_320 * math.cos(math.radians(lat)))
    return round(lat / lat_step) * lat_step, round(lon / lon_step) * lon_step


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
if "radius" not in st.session_state:
    st.session_state.radius = 500
if "result" not in st.session_state:
    st.session_state.result = None


def move_to(cx: float, cy: float) -> None:
    st.session_state.cx = cx
    st.session_state.cy = cy
    st.session_state.result = None


moved_address = st.session_state.pop("moved_address", None)
if moved_address:
    st.toast(f"'{moved_address}' 위치로 이동했습니다.")

# 지도를 그리기 전에, 직전 렌더에서 파악된 지도 중심(없으면 확정 위치)을 기준으로 삼는다.
# 이렇게 하면 조회 조건 패널(업종 빈도 미리보기·조회 버튼)을 지도보다 먼저 배치할 수 있다.
basis_center = st.session_state.get("live_center") or (st.session_state.cy, st.session_state.cx)

with st.sidebar:
    st.title("공공API기반의 상권분석")
    st.markdown("**반경 (m)**")
    radius = st.slider(
        "반경 (m)", min_value=200, max_value=600, value=st.session_state.radius, step=50, label_visibility="collapsed"
    )
    st.session_state.radius = radius

    st.markdown("**주소 / 장소 검색** (예: 역삼동, 삼성역)")
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
        candidates = st.session_state.address_candidates
        labels = [
            f"{c['title']} — {c['address']}" if c["address"] and c["address"] != c["title"] else c["title"]
            for c in candidates
        ]
        picked_idx = st.selectbox(
            "검색 결과 중 선택하세요", range(len(candidates)), format_func=lambda i: labels[i], key="picked_candidate"
        )
        if st.button("선택"):
            chosen = candidates[picked_idx]
            move_to(chosen["cx"], chosen["cy"])
            st.session_state.moved_address = chosen["title"]
            st.session_state.address_candidates = None
            st.rerun()

    if st.button("초기 위치(강남역)로"):
        move_to(*GANGNAM_STATION)
        st.session_state.radius = 500
        st.rerun()

    st.divider()
    try:
        with st.spinner("업종 빈도 계산 중..."):
            snapped_lat, snapped_lon = _snap_to_grid(basis_center[0], basis_center[1])
            preview_shops = _fetch_shops_cached(snapped_lon, snapped_lat, radius)
            freq = analyze(preview_shops, None)["by_category"].set_index("상권업종소분류명")["개수"]
            ordered_categories = sorted(_food_categories(), key=lambda c: (-freq.get(c, 0), c))
    except Exception as e:
        ordered_categories = _food_categories()
        st.warning(f"이 지역 업종 빈도를 불러오지 못해 기본 순서로 표시합니다. ({e})")

    st.markdown("**내 업종** (다중 선택 가능, 이 지역 빈도순)")
    if st.button("이 지역 상위 5개 자동선택") and ordered_categories:
        st.session_state.my_categories = ordered_categories[:5]
    my_categories = st.multiselect("업종", ordered_categories, key="my_categories", label_visibility="collapsed")

    if st.button("조회하기", type="primary"):
        st.session_state.cx, st.session_state.cy = basis_center[1], basis_center[0]
        with st.spinner("분석 중..."):
            # basis_center는 캐시 히트율을 위해 스냅된 근사 좌표로 미리보기를 조회했을 수 있으므로,
            # 확정 시점에는 정확한 좌표로 다시 조회한다.
            shops = _fetch_shops_cached(st.session_state.cx, st.session_state.cy, radius)
            result = analyze(shops, None)
            my_stats = []
            for cat in my_categories:
                r = analyze(shops, cat)
                my_stats.append({"category": cat, "rank": r["my_rank"], "count": r["my_count"], "pct": r["my_pct"]})
            st.session_state.result = (result, radius, my_categories, my_stats)
            st.session_state.result_query_snapshot = (
                round(basis_center[0], 5),
                round(basis_center[1], 5),
                radius,
                tuple(sorted(my_categories)),
            )
        st.rerun()

vworld_key = os.getenv("VWORLD_API_KEY")
m = folium.Map(
    location=[st.session_state.cy, st.session_state.cx],
    zoom_start=16,
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

# 반경 원이 항상 화면 안에 들어오도록 자동으로 맞춘다. 슬라이더 값이 아니라 고정값을 쓴다 —
# radius를 쓰면 반경 조절마다 base map 콘텐츠(해시 대상)가 바뀌어 지도가 리마운트되고 줌이 리셋된다.
lat_pad = FIT_BOUNDS_RADIUS_M / 111_320
lon_pad = FIT_BOUNDS_RADIUS_M / (111_320 * math.cos(math.radians(st.session_state.cy)))
m.fit_bounds(
    [
        [st.session_state.cy - lat_pad, st.session_state.cx - lon_pad],
        [st.session_state.cy + lat_pad, st.session_state.cx + lon_pad],
    ]
)

if st.session_state.result:
    result, used_radius, used_categories, used_stats = st.session_state.result
    category_colors = {cat: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, cat in enumerate(used_categories)}
    my_shops = result["food_df"][result["food_df"]["상권업종소분류명"].isin(used_categories)]

    if not my_shops.empty:
        if len(my_shops) > CLUSTER_THRESHOLD:
            layer = MarkerCluster(name="내 업종", maxClusterRadius=40, disableClusteringAtZoom=18).add_to(m)
        else:
            layer = folium.FeatureGroup(name="내 업종").add_to(m)
        for _, row in my_shops.iterrows():
            shop_name = html.escape(str(row["상호"]))
            shop_category = html.escape(str(row["상권업종소분류명"]))
            folium.CircleMarker(
                location=[row["위도"], row["경도"]],
                radius=6,
                color=category_colors.get(row["상권업종소분류명"], MY_COLOR),
                fill=True,
                fill_opacity=0.85,
                tooltip=folium.Tooltip(row["상호"], permanent=False, direction="top", sticky=False),
                popup=folium.Popup(f"<b>{shop_name}</b><br>{shop_category}", max_width=220),
            ).add_to(layer)

    if len(used_categories) > 1:
        legend_rows = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{category_colors[c]};'
            f'display:inline-block;"></span><span>{html.escape(c)}</span></div>'
            for c in used_categories
        )
        m.get_root().html.add_child(
            folium.Element(
                f"""
                <div style="position:fixed; top:12px; right:12px; z-index:1000;
                            background:rgba(255,255,255,0.9); border:1px solid #ccc; border-radius:6px;
                            padding:8px 10px; font-size:12px; pointer-events:none;">
                {legend_rows}
                </div>
                """
            )
        )

# 반경 원은 feature_group_to_add로 그린다 — 이 값은 streamlit-folium 컴포넌트의 리마운트 여부를
# 결정하는 콘텐츠 해시에 포함되지 않아서(__init__.py의 hash_key 계산 참고), 위치나 반경이 바뀌어도
# 지도가 리마운트되지 않고 원만 매끄럽게 갱신된다. live_center(직전 렌더 값)를 기준으로 그려서
# 드래그를 따라가고, radius(슬라이더 값)로 크기가 바뀐다.
circle_center = list(st.session_state.get("live_center") or (st.session_state.cy, st.session_state.cx))
radius_group = folium.FeatureGroup(name="radius_circle")
folium.Circle(circle_center, radius=radius, color=CENTER_COLOR, fill=True, fill_opacity=0.1).add_to(radius_group)

# feature_group_to_add는 매 렌더마다 레이어를 "추가"만 하고 이전 것을 지우지 않으므로(라이브러리가
# window.feature_group 배열에 계속 push), 그대로 두면 원이 계속 쌓인다. 이 정리 로직은 반경/위치와
# 무관한 고정 텍스트라 base map 콘텐츠 해시에 영향을 주지 않는다(한 번만 등록되면 됨).
m.get_root().html.add_child(
    folium.Element(
        """
    <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
         style="display:none" onload="
        (function() {
            function turfPruneFeatureGroups() {
                if (typeof map_div === 'undefined') { setTimeout(turfPruneFeatureGroups, 50); return; }
                map_div.on('layeradd', function() {
                    if (window.feature_group && window.feature_group.length > 1) {
                        var keep = window.feature_group[window.feature_group.length - 1];
                        window.feature_group.forEach(function(layer) {
                            if (layer !== keep) { map_div.removeLayer(layer); }
                        });
                        window.feature_group = [keep];
                    }
                });
            }
            turfPruneFeatureGroups();
        })();
        ">
        """
    )
)

map_data = st_folium(
    m,
    height=560,
    use_container_width=True,
    center=[st.session_state.cy, st.session_state.cx],
    feature_group_to_add=radius_group,
    key="main_map",
)

live_center = _bounds_center(map_data.get("bounds")) or (st.session_state.cy, st.session_state.cx)
st.session_state.live_center = live_center

st.divider()
st.subheader("📊 분석 결과")

if st.session_state.result:
    current_snapshot = (
        round(basis_center[0], 5),
        round(basis_center[1], 5),
        radius,
        tuple(sorted(my_categories)),
    )
    if st.session_state.get("result_query_snapshot") != current_snapshot:
        st.warning("위치·반경·업종이 마지막 조회 이후 바뀌었습니다 — 다시 조회해보세요.")

    result, used_radius, used_categories, used_stats = st.session_state.result
    st.caption(f"조회 위치: 위도 {st.session_state.cy:.5f}, 경도 {st.session_state.cx:.5f} · 반경 {used_radius}m")

    st.metric("총 음식점", f"{result['total']}곳")
    for stat in used_stats:
        cols = st.columns(3)
        cols[0].markdown(f"**{stat['category']}**")
        if stat["rank"]:
            cols[1].metric("개수", f"{stat['count']}곳", f"{stat['rank']}위", delta_color="off")
            cols[2].metric("비중", f"{stat['pct']}%", delta_color="off")
        else:
            cols[1].metric("개수", "0곳", "반경 내 없음", delta_color="off")

    st.markdown("**업종별 개수·비율** (반경 내, 많은 순)")
    chart_df = result["by_category"].copy().reset_index(drop=True)
    chart_df["순위"] = chart_df.index + 1
    chart_df["표시명"] = chart_df["순위"].astype(str) + "위 " + chart_df["상권업종소분류명"]
    chart_df["라벨"] = chart_df["개수"].astype(str) + "곳 (" + chart_df["비율"].astype(str) + "%)"
    chart_df["내업종"] = chart_df["상권업종소분류명"].isin(used_categories)
    # 지도 범례와 같은 색상 매핑을 사용 — 선택하지 않은 업종은 중립색
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

    my_shops_table = result["food_df"][result["food_df"]["상권업종소분류명"].isin(used_categories)]
    if not my_shops_table.empty:
        st.markdown("**업소 목록**")
        display_table = (
            my_shops_table[["상호", "상권업종소분류명", "도로명주소"]]
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

    report_text = generate_report(result, used_radius, None)
    for stat in used_stats:
        if stat["rank"]:
            report_text += (
                f"\n★ 내 업종({stat['category']}): {stat['count']}곳, "
                f"{stat['rank']}위, {stat['pct']}% 차지"
            )
    with st.expander("원본 리포트 텍스트"):
        st.text(report_text)
else:
    st.caption("아직 조회 결과가 없습니다. 위 조건을 설정하고 '조회하기'를 눌러주세요.")

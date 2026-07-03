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
from collector.geocoder import geocode_address
from collector.shop_fetcher import fetch_shops
from presenter.report import generate_report

GANGNAM_STATION = (127.027619, 37.497925)  # (cx, cy)
MY_COLOR = "#c0392b"
NEUTRAL_COLOR = "#9aa5a0"
CATEGORY_PALETTE = ["#c0392b", "#2f6e5b", "#b07d1f", "#5b4b8a", "#1f6f91", "#8a4b6b", "#4b8a4f", "#8a6b4b"]
CLUSTER_THRESHOLD = 40
LABEL_ZOOM_THRESHOLD = 17  # 이 줌 레벨부터는 hover 없이도 상호명을 항상 표시

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


with st.sidebar:
    st.markdown(
        "<div style='font-size:20px; font-weight:700; margin-bottom:8px;'>공공API기반의 상권분석</div>",
        unsafe_allow_html=True,
    )
    st.markdown("**① 조회 주소** (동 단위까지 가능, 예: 서울특별시 강남구 역삼동)")
    address = st.text_input("주소", label_visibility="collapsed")
    if st.button("주소로 이동") and address:
        try:
            coord = geocode_address(address)
        except RuntimeError as e:
            st.error(str(e))
        else:
            if coord:
                move_to(*coord)
                st.rerun()
            else:
                st.warning("주소를 찾을 수 없습니다.")

    st.divider()
    st.markdown("**② 위치 · 반경**")
    st.caption("지도 중앙의 ⊕ 표시가 원하는 위치를 가리키도록 지도를 움직이고, 반경을 조절하세요.")
    radius = st.slider(
        "반경 (m)", min_value=300, max_value=1000, value=st.session_state.radius, step=50, label_visibility="collapsed"
    )
    st.session_state.radius = radius

    st.divider()
    condition_slot = st.empty()

vworld_key = os.getenv("VWORLD_API_KEY")
m = folium.Map(
    location=[st.session_state.cy, st.session_state.cx],
    zoom_start=16,
    tiles=None if vworld_key else "OpenStreetMap",
)

if vworld_key:
    folium.TileLayer(
        tiles=f"https://api.vworld.kr/req/wmts/1.0.0/{vworld_key}/Base/{{z}}/{{y}}/{{x}}.png",
        attr="VWorld",
        name="VWorld 배경지도",
        overlay=False,
        control=False,
    ).add_to(m)

location = [st.session_state.cy, st.session_state.cx]
folium.Circle(location, radius=radius, color="blue", fill=True, fill_opacity=0.1).add_to(m)

# 반경 원이 항상 화면 안에 들어오도록 자동으로 맞춘다
lat_pad = radius / 111_320
lon_pad = radius / (111_320 * math.cos(math.radians(st.session_state.cy)))
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
                tooltip=folium.Tooltip(row["상호"], permanent=True, direction="top", sticky=False),
                popup=folium.Popup(f"<b>{shop_name}</b><br>{shop_category}", max_width=220),
            ).add_to(layer)

        # 상호명은 항상 지도에 붙어 있지만(permanent tooltip), 일정 배율 이상으로 확대했을 때만
        # 실제로 보이도록 CSS로 토글한다 — 배율이 낮을 때 라벨이 다닥다닥 겹치는 것을 막기 위함이다.
        m.get_root().html.add_child(
            folium.Element(
                f"""
                <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
                     style="display:none" onload="
                    (function() {{
                        function turfUpdateLabelVisibility() {{
                            var pane = document.querySelector('#map_div .leaflet-tooltip-pane');
                            if (typeof map_div === 'undefined' || !pane) return;
                            pane.style.display = map_div.getZoom() >= {LABEL_ZOOM_THRESHOLD} ? '' : 'none';
                        }}
                        function turfWaitForMapLabels() {{
                            if (typeof map_div === 'undefined') {{ setTimeout(turfWaitForMapLabels, 50); return; }}
                            map_div.on('zoomend', turfUpdateLabelVisibility);
                            turfUpdateLabelVisibility();
                        }}
                        turfWaitForMapLabels();
                    }})();
                    ">
                """
            )
        )

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

# 지도 정중앙에 고정된 원 + 십자선 — 지도를 스크롤해도 이 둘은 화면 중앙에 붙어서 함께 움직이고,
# 지도만 그 밑에서 흘러간다. 이 위치가 "찾기"를 누르는 순간 실제 좌표로 확정된다.
# 이미 결과가 나온 뒤(영역이 확정된 뒤)에는 확정된 원(음영)만 보여주고 이 미리보기는 생략한다 —
# 줌 배율이 크게 바뀌면 화면 고정 미리보기 원과 실제 지도 좌표에 고정된 원의 크기가 어긋나 보여서
# 둘을 같이 보여주면 오히려 혼란스럽다.
# streamlit-folium은 지도의 실제 Leaflet 변수명을 "map_div"로 고정해서 렌더링한다
# (folium.Map.get_name()이 반환하는 이름과는 다르다).
map_var = "map_div"
if not st.session_state.result:
    m.get_root().html.add_child(
        folium.Element(
            f"""
        <div id="turf-radius-preview" style="position:fixed; border-radius:50%; border:2px solid {MY_COLOR};
                    background:rgba(192,57,43,0.12); z-index:999; pointer-events:none;"></div>
        <div id="turf-crosshair" style="position:fixed; z-index:1000; pointer-events:none; font-size:26px;
                    line-height:1; color:{MY_COLOR}; text-shadow:0 0 3px #fff, 0 0 3px #fff, 0 0 4px #fff;
                    transform:translate(-50%,-50%);">
          ⊕
        </div>
        <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
             style="display:none" onload="
            (function() {{
                function turfPositionOverlay() {{
                    var mapEl = document.getElementById('{map_var}');
                    var circleEl = document.getElementById('turf-radius-preview');
                    var crossEl = document.getElementById('turf-crosshair');
                    if (typeof {map_var} === 'undefined' || !mapEl || !circleEl) return;

                    var rect = mapEl.getBoundingClientRect();
                    var centerX = rect.left + rect.width / 2;
                    var centerY = rect.top + rect.height / 2;

                    var metersPerPixel = 156543.03392 * Math.cos({map_var}.getCenter().lat * Math.PI / 180) / Math.pow(2, {map_var}.getZoom());
                    var radiusPx = {radius} / metersPerPixel;

                    circleEl.style.left = centerX + 'px';
                    circleEl.style.top = centerY + 'px';
                    circleEl.style.width = (radiusPx * 2) + 'px';
                    circleEl.style.height = (radiusPx * 2) + 'px';
                    circleEl.style.transform = 'translate(-50%, -50%)';

                    if (crossEl) {{
                        crossEl.style.left = centerX + 'px';
                        crossEl.style.top = centerY + 'px';
                    }}
                }}
                function turfWaitForMap() {{
                    if (typeof {map_var} === 'undefined') {{ setTimeout(turfWaitForMap, 50); return; }}
                    {map_var}.on('zoom', turfPositionOverlay);
                    window.addEventListener('resize', turfPositionOverlay);
                    turfPositionOverlay();
                }}
                turfWaitForMap();
            }})();
            ">
            """
        )
    )

map_data = st_folium(m, width=800, height=560, center=[st.session_state.cy, st.session_state.cx], key="main_map")

live_center = _bounds_center(map_data.get("bounds")) or (st.session_state.cy, st.session_state.cx)

with condition_slot.container():
    try:
        with st.spinner("업종 빈도 계산 중..."):
            preview_shops = _fetch_shops_cached(live_center[1], live_center[0], radius)
            freq = analyze(preview_shops, None)["by_category"].set_index("상권업종소분류명")["개수"]
            ordered_categories = sorted(_food_categories(), key=lambda c: (-freq.get(c, 0), c))
    except Exception as e:
        preview_shops = None
        ordered_categories = _food_categories()
        st.warning(f"이 지역 업종 빈도를 불러오지 못해 기본 순서로 표시합니다. ({e})")

    st.markdown("**③ 내 업종** (다중 선택 가능, 이 지역 빈도순)")
    my_categories = st.multiselect("업종", ordered_categories, key="my_categories", label_visibility="collapsed")

    if st.button("④ 찾기"):
        st.session_state.cx, st.session_state.cy = live_center[1], live_center[0]
        with st.spinner("분석 중..."):
            shops = preview_shops if preview_shops is not None else _fetch_shops_cached(
                st.session_state.cx, st.session_state.cy, radius
            )
            result = analyze(shops, None)
            my_stats = []
            for cat in my_categories:
                r = analyze(shops, cat)
                my_stats.append({"category": cat, "rank": r["my_rank"], "count": r["my_count"], "pct": r["my_pct"]})
            st.session_state.result = (result, radius, my_categories, my_stats)
        st.rerun()

if st.session_state.result:
    result, used_radius, used_categories, used_stats = st.session_state.result
    st.subheader("분석 결과")

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
        color=alt.condition("datum.내업종", alt.value(MY_COLOR), alt.value(NEUTRAL_COLOR)),
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

    with st.container(height=480):
        st.altair_chart(chart, use_container_width=True)

    my_shops_table = result["food_df"][result["food_df"]["상권업종소분류명"].isin(used_categories)]
    if not my_shops_table.empty:
        st.markdown("**업소 목록**")
        st.dataframe(
            my_shops_table[["상호", "상권업종소분류명"]]
            .rename(columns={"상호": "상호명", "상권업종소분류명": "업종"})
            .reset_index(drop=True),
            use_container_width=True,
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

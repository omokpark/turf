"""본문 지도 뷰 — folium 지도 구성 + st_folium 호출

지도는 표시 전용이고(팬·줌 = 순수 탐색), 분석 중심·반경 조작은 원/핀 드래그와
지도 클릭으로 한다. 그 상호작용 JS는 ui/map_interactions.js에 격리되어 있으며
여기서 string.Template로 반경 한계만 주입한다. 반환값 해석은 ui/channels.py.
"""

import html
from pathlib import Path
from string import Template

import folium
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium

from core import config, schema
from core.area import MAX_RADIUS_M, MIN_RADIUS_M, zoom_for_radius
from ui.state import CENTER_COLOR, CLUSTER_THRESHOLD, CROSSHAIR_HTML, NEUTRAL_COLOR

_INTERACTIONS_TEMPLATE = Template((Path(__file__).parent / "map_interactions.js").read_text(encoding="utf-8"))


def _base_map(radius: int) -> folium.Map:
    try:
        vworld_key = config.vworld_key()
    except RuntimeError:
        vworld_key = None
    m = folium.Map(
        location=[st.session_state.cy, st.session_state.cx],
        zoom_start=zoom_for_radius(radius),
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
    return m


def _add_center_controls(m: folium.Map, radius: int) -> None:
    """반경 원 + 십자 핀 + 드래그 상호작용 JS. 원과 핀은 지리 좌표에 고정된다."""
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
    m.get_root().html.add_child(
        folium.Element(_INTERACTIONS_TEMPLATE.substitute(min_r=MIN_RADIUS_M, max_r=MAX_RADIUS_M))
    )


def _add_shop_layers(m: folium.Map, analysis: dict, selected_categories: list[str], category_colors: dict) -> None:
    food_df = analysis["food_df"]

    # 전체 음식점 밀집도 히트맵 — 상권의 '뜨거운 정도'를 한눈에
    heat_group = folium.FeatureGroup(name="전체 음식점 밀집도").add_to(m)
    HeatMap(food_df[[schema.LAT, schema.LON]].values.tolist(), radius=22, blur=18, min_opacity=0.3).add_to(heat_group)

    my_shops = food_df[food_df[schema.CAT_S].isin(selected_categories)]
    if not my_shops.empty:
        if len(my_shops) > CLUSTER_THRESHOLD:
            layer = MarkerCluster(name="선택 업종", maxClusterRadius=40, disableClusteringAtZoom=18).add_to(m)
        else:
            layer = folium.FeatureGroup(name="선택 업종").add_to(m)
        for _, row in my_shops.iterrows():
            shop_name = html.escape(str(row[schema.NAME]))
            shop_category = html.escape(str(row[schema.CAT_S]))
            folium.CircleMarker(
                location=[row[schema.LAT], row[schema.LON]],
                radius=6,
                color=category_colors.get(row[schema.CAT_S], NEUTRAL_COLOR),
                fill=True,
                fill_opacity=0.85,
                tooltip=folium.Tooltip(row[schema.NAME], permanent=False, direction="top", sticky=False),
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


def render_map(radius: int, analysis: dict, selected_categories: list[str], category_colors: dict) -> dict:
    """지도를 그리고 st_folium 반환값(map_data)을 돌려준다."""
    m = _base_map(radius)
    _add_center_controls(m, radius)
    if analysis["total"] > 0:
        _add_shop_layers(m, analysis, selected_categories, category_colors)
    return st_folium(m, height=560, use_container_width=True, key="main_map")

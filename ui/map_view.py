"""본문 지도 뷰 — folium 지도 구성 + st_folium 호출

지도는 인허가(MOI) 데이터 위에서 돈다 (SEMAS 실시간 스냅샷은 개폐업 이력이 없어
신규·폐업을 못 그린다). 표시 대상은 '주류 가능 업소'(liquor_affinity≥임계)이고,
최근 개업🟢·폐업🔴·그 외 영업중⚪을 색으로 구분한다 — 영업사원이 "뭐가 새로 생겼고
뭐가 빠졌나"를 지도에서 바로 읽게 하기 위함.

지도는 표시 전용이고(팬·줌 = 순수 탐색), 분석 중심·반경 조작은 원/핀 드래그와
지도 클릭으로 한다. 그 상호작용 JS는 ui/map_interactions.js에 격리되어 있으며
여기서 string.Template로 반경 한계만 주입한다. 반환값 해석은 ui/channels.py.
"""

import html
from pathlib import Path
from string import Template

import folium
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from core import config, schema
from core.area import MAX_RADIUS_M, MIN_RADIUS_M, zoom_for_radius
from ui.state import CENTER_COLOR, CLUSTER_THRESHOLD, CROSSHAIR_HTML

_INTERACTIONS_TEMPLATE = Template((Path(__file__).parent / "map_interactions.js").read_text(encoding="utf-8"))

# 업소 상태별 색 (구역 동향·dataviz 검증 팔레트와 통일)
STATUS_COLOR = {"신규": "#1a7f5c", "폐업": "#b3541e", "영업": "#5b6670"}


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


def _add_shop_layers(m: folium.Map, display_df) -> None:
    """주류 가능 업소 마커 — 상태(신규🟢/폐업🔴/영업⚪)별 색. display_df 컬럼:
    NAME, CAT_S, LAT, LON, 상태."""
    if len(display_df) > CLUSTER_THRESHOLD:
        layer = MarkerCluster(name="업소", maxClusterRadius=40, disableClusteringAtZoom=18).add_to(m)
    else:
        layer = folium.FeatureGroup(name="업소").add_to(m)
    for _, row in display_df.iterrows():
        status = row["상태"]
        shop_name = html.escape(str(row[schema.NAME]))
        shop_cat = html.escape(str(row[schema.CAT_S]))
        folium.CircleMarker(
            location=[row[schema.LAT], row[schema.LON]],
            radius=6,
            color=STATUS_COLOR.get(status, STATUS_COLOR["영업"]),
            fill=True,
            fill_opacity=0.85,
            tooltip=folium.Tooltip(shop_name, permanent=False, direction="top", sticky=False),
            popup=folium.Popup(f"<b>{shop_name}</b><br>{shop_cat} · {html.escape(status)}", max_width=220),
        ).add_to(layer)

    # 범례 — 상태별 색 안내
    legend_rows = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<span style="width:10px;height:10px;border-radius:50%;background:{STATUS_COLOR[s]};'
        f'display:inline-block;"></span><span>{s}</span></div>'
        for s in ("신규", "폐업", "영업")
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


def render_map(radius: int, display_df) -> dict:
    """지도를 그리고 st_folium 반환값(map_data)을 돌려준다. display_df가 비면 마커 없이 지도만."""
    m = _base_map(radius)
    _add_center_controls(m, radius)
    if display_df is not None and len(display_df) > 0:
        _add_shop_layers(m, display_df)
    return st_folium(m, height=560, use_container_width=True, key="main_map")

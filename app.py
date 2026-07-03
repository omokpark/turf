"""Streamlit + folium 지도 UI (Day 3)"""

import folium
import streamlit as st
from streamlit_folium import st_folium

from analyzer.terrain import analyze
from collector.shop_fetcher import fetch_shops
from presenter.report import generate_report

SEOUL_CENTER = [37.5665, 126.9780]

st.set_page_config(page_title="turf", layout="wide")
st.title("turf — 경쟁 지형 조회")

if "cx" not in st.session_state:
    st.session_state.cx = None
    st.session_state.cy = None
if "result" not in st.session_state:
    st.session_state.result = None

with st.sidebar:
    radius = st.slider("반경 (m)", min_value=300, max_value=1000, value=500, step=50)
    my_category = st.text_input("내 업종 (선택)")
    analyze_clicked = st.button("분석 시작")

m = folium.Map(location=SEOUL_CENTER, zoom_start=13)

if st.session_state.cx is not None:
    location = [st.session_state.cy, st.session_state.cx]
    folium.Marker(location).add_to(m)
    folium.Circle(location, radius=radius, color="blue", fill=True, fill_opacity=0.1).add_to(m)

map_data = st_folium(m, width=800, height=500)

clicked = map_data.get("last_clicked") if map_data else None
if clicked and (clicked["lat"], clicked["lng"]) != (st.session_state.cy, st.session_state.cx):
    st.session_state.cy = clicked["lat"]
    st.session_state.cx = clicked["lng"]
    st.rerun()

if st.session_state.cx is not None:
    st.caption(f"선택 좌표: cx={st.session_state.cx:.4f}, cy={st.session_state.cy:.4f}")
else:
    st.caption("지도를 클릭해서 분석할 위치를 선택하세요.")

if analyze_clicked:
    if st.session_state.cx is None:
        st.warning("지도를 클릭해서 위치를 먼저 선택하세요.")
    else:
        with st.spinner("분석 중..."):
            shops = fetch_shops(st.session_state.cx, st.session_state.cy, radius)
            result = analyze(shops, my_category or None)
            st.session_state.result = (result, radius, my_category or None)

if st.session_state.result:
    result, used_radius, used_category = st.session_state.result
    st.subheader("분석 결과")
    st.text(generate_report(result, used_radius, used_category))
    st.bar_chart(result["by_category"].set_index("상권업종소분류명")["개수"])

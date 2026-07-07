"""탐색 페이지 — 지도 탭(밀집도·분포 + 중심·반경 조작) + 업종 구성 탭(스냅샷 집계)"""

import streamlit as st

from core import schema
from core.area import MAX_RADIUS_M, MIN_RADIUS_M, walk_minutes
from presenter.report import generate_report
from ui import channels
from ui.components.charts import category_bar_chart
from ui.components.shop_table import render_shop_table
from ui.map_view import render_map


def render_map_tab(radius: int, analysis: dict, selected_categories: list[str], category_colors: dict) -> None:
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
    walk_col.markdown(f"**{radius}m** · 도보 {walk_minutes(radius)}분")

    map_data = render_map(radius, analysis, selected_categories, category_colors)

    st.caption(
        f"📍 중심: 위도 {st.session_state.cy:.5f}, 경도 {st.session_state.cx:.5f} · "
        f"반경 {radius}m (도보 약 {walk_minutes(radius)}분)"
    )
    st.caption("🎯 원 끌기 = 중심 이동  ·  ↔️ 가장자리 끌기 = 반경 조절  ·  📌 원 밖 클릭 = 점프  ·  🧭 지도 끌기/줌 = 탐색")

    channels.apply_radius_message(map_data)
    channels.apply_center_click(map_data)


def render_stats_tab(radius: int, analysis: dict, selected_categories: list[str], category_colors: dict) -> None:
    if analysis["total"] == 0:
        st.info("반경 내 음식점이 없습니다. 위치나 반경을 바꿔보세요.")
        return

    by_category = analysis["by_category"]
    st.caption(
        f"조회 위치: 위도 {st.session_state.cy:.5f}, 경도 {st.session_state.cx:.5f} · "
        f"반경 {radius}m (도보 약 {walk_minutes(radius)}분)"
    )

    st.metric("총 음식점", f"{analysis['total']}곳")
    for cat in selected_categories:
        match = by_category[by_category[schema.CAT_S] == cat]
        cols = st.columns(3)
        cols[0].markdown(f"**{cat}**")
        row = match.iloc[0]
        cols[1].metric("개수", f"{int(row['개수'])}곳", f"{match.index[0] + 1}위", delta_color="off")
        cols[2].metric("비중", f"{row['비율']}%", delta_color="off")

    st.markdown("**📊 업종별 개수·비율** (반경 내, 많은 순)")
    chart, chart_height = category_bar_chart(by_category, category_colors)
    if chart_height > 480:
        st.caption("전체 업종을 보려면 아래 차트를 스크롤하세요.")
    with st.container(height=480):
        st.altair_chart(chart, use_container_width=True)

    render_shop_table(analysis["food_df"], selected_categories)

    report_text = generate_report(analysis, radius, None)
    for cat in selected_categories:
        match = by_category[by_category[schema.CAT_S] == cat]
        row = match.iloc[0]
        report_text += f"\n★ 내 업종({cat}): {int(row['개수'])}곳, {match.index[0] + 1}위, {row['비율']}% 차지"
    with st.expander("원본 리포트 텍스트"):
        st.text(report_text)

"""'변화' 탭 — 연도별 개폐업 추이 + 최근 개업(골든타임) + 자리회전 리스트

방문 반경(도보 상권) 스케일의 인허가 이력을 보여준다. 구역 아웃룩(800m, 국면 진단)과
달리 실제 방문 결정에 쓰는 좁은 반경 기준이다.
"""

import altair as alt
import pandas as pd
import streamlit as st

from core import schema
from core.area import Area, filter_radius
from datasources import moi_store
from timeline import trend

COLOR_OPEN = "#1a7f5c"
COLOR_CLOSE = "#b3541e"

RECENT_DAYS = 90


@st.cache_data(ttl=600, show_spinner=False)
def _load_roster(cache_key: tuple) -> pd.DataFrame:
    return moi_store.load_roster()


def render_changes(cx: float, cy: float, radius: int) -> None:
    roster = _load_roster(moi_store.cache_token())
    if len(roster) == 0:
        st.info("인허가 데이터가 아직 수집되지 않았습니다. '구역 아웃룩' 탭의 안내를 참고하세요.")
        return

    area = Area(cx=cx, cy=cy, radius=radius)
    local = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]), area)
    st.caption(
        f"기준: 중심 반경 {radius}m · 인허가 이력 {len(local):,}건 · "
        f"수집 시점 {moi_store.freshness():%Y-%m-%d %H:%M} · 폐업 신고는 실제보다 수개월 늦게 반영될 수 있음"
    )

    if len(local) == 0:
        st.warning(f"반경 {radius}m 내 인허가 이력이 없습니다.")
        return

    st.markdown("#### 연도별 개업·폐업 추이")
    yearly = trend.yearly_trend(local, years=6)
    long = yearly.melt(id_vars="연도", value_vars=["개업", "폐업"], var_name="구분", value_name="건수")
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("연도:O", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("건수:Q"),
            xOffset="구분:N",
            color=alt.Color(
                "구분:N",
                scale=alt.Scale(domain=["개업", "폐업"], range=[COLOR_OPEN, COLOR_CLOSE]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["연도:O", "구분:N", "건수:Q"],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch")

    st.divider()
    st.markdown(f"#### 최근 개업 (최근 {RECENT_DAYS}일 — 방문 골든타임)")
    recent = trend.recent_openings(local, days=RECENT_DAYS)
    if len(recent) == 0:
        st.caption("최근 개업 건이 없습니다.")
    else:
        st.dataframe(
            recent[[schema.NAME, schema.CAT_S, schema.ADDR_ROAD, schema.LICENSED_AT, "개업경과일"]].rename(
                columns={schema.NAME: "상호", schema.CAT_S: "업태", schema.ADDR_ROAD: "주소", schema.LICENSED_AT: "인허가일자"}
            ),
            width="stretch",
            hide_index=True,
        )

    st.divider()
    st.markdown("#### 자리 회전 (같은 주소, 과거 폐업 이력 있는 곳)")
    turnover = trend.site_turnover(local)
    turnover = turnover[turnover["자리회전수"] > 0]
    if len(turnover) == 0:
        st.caption("자리회전 이력이 있는 업소가 없습니다.")
    else:
        st.dataframe(
            turnover[[schema.NAME, schema.CAT_S, schema.ADDR_ROAD, "자리회전수"]].rename(
                columns={schema.NAME: "상호", schema.CAT_S: "업태", schema.ADDR_ROAD: "주소"}
            ),
            width="stretch",
            hide_index=True,
        )

"""'방문 우선순위' 탭 — 가용 신호를 스코어러로 합산해 근거 배지와 함께 랭킹으로 보여준다.

판단 원칙: 점수는 항상 근거 배지와 함께 나온다 (Scorer 계약이 강제). 추천·예측
문구는 쓰지 않는다. 구역 아웃룩의 국면은 랭킹 위에 맥락으로만 병기한다 — 개별 업소의
근거가 아니라 "이 구역 전체가 지금 어떤 판인가"라는 별도 정보이기 때문이다.
"""

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core import schema
from core.area import Area, OUTLOOK_RADIUS_M, filter_radius
from datasources import moi_store, naver, seoul
from scorers.base import available_scorers, validate_score_result
from signals.base import AreaContext
from signals.outlook import phase_trajectory
from signals.registry import available_signals

# 신호·스코어러 모듈 import = 레지스트리 등록 (파일 1개 추가 = 랭킹에 자동 반영)
import signals.buzz_momentum  # noqa: F401
import signals.conversion_vector  # noqa: F401
import signals.franchise  # noqa: F401
import signals.growth_momentum  # noqa: F401
import signals.liquor_adjacency  # noqa: F401
import signals.night_index  # noqa: F401
import signals.recent_opening  # noqa: F401
import signals.review_momentum  # noqa: F401
import signals.survivor  # noqa: F401
import scorers.destination_index  # noqa: F401
import scorers.weighted_sum  # noqa: F401

TOP_N = 30
MARKER_COLOR = "#c0392b"


@st.cache_data(ttl=600, show_spinner=False)
def _load_roster(cache_key: tuple) -> pd.DataFrame:
    return moi_store.load_roster()


def render_ranking(cx: float, cy: float, radius: int) -> None:
    roster = _load_roster(moi_store.cache_token())
    if len(roster) == 0:
        st.info("인허가 데이터가 아직 수집되지 않았습니다. '구역 아웃룩' 탭의 안내를 참고하세요.")
        return

    area = Area(cx=cx, cy=cy, radius=radius)
    local = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]), area)
    if len(local) == 0:
        st.warning(f"반경 {radius}m 내 인허가 이력이 없습니다.")
        return

    outlook_area = Area(cx=cx, cy=cy, radius=OUTLOOK_RADIUS_M)
    outlook_local = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]), outlook_area)
    traj = phase_trajectory(outlook_local, years=6)
    if len(traj) > 0:
        st.caption(f"구역 국면(반경 {OUTLOOK_RADIUS_M}m 기준, 참고용 맥락): **{traj.iloc[-1]['국면']}**")

    ctx = AreaContext(area=area, establishments=local, rosters={"moi": local}, reference=roster)
    # 키가 있으면 해당 신호가 자동으로 켜진다: naver(리뷰·버즈·목적지 지수), seoul(야간 지수)
    providers = {"moi"}
    if naver.available():
        providers.add("naver")
    if seoul.available():
        providers.add("seoul")
    signals_avail = available_signals(providers)
    if not signals_avail:
        st.info("가용한 신호가 없습니다.")
        return

    scorers_avail = available_scorers()
    if not scorers_avail:
        st.info("가용한 스코어러가 없습니다.")
        return
    scorer = st.radio(
        "랭킹 기준",
        scorers_avail,
        format_func=lambda s: s.label,
        horizontal=True,
        key="ranking_scorer",
    )

    spinner_msg = "신호 계산 중..."
    if "naver" in providers:
        spinner_msg = "신호 계산 중... (블로그 조회는 처음 한 번만 느리고 7일간 캐시됩니다)"
    with st.spinner(spinner_msg):
        signal_results = {sig.id: result for sig in signals_avail if len(result := sig.compute(ctx)) > 0}
        scored = scorer.score(signal_results, ctx)
    validate_score_result(scored)

    if len(scored) == 0:
        st.info("근거를 만들 수 있는 업소가 없습니다.")
        return

    st.caption(f"{scorer.label} — {scorer.description}")

    top = scored.head(TOP_N).merge(
        local[[schema.SRC_ID, schema.NAME, schema.CAT_S, schema.ADDR_ROAD, schema.LAT, schema.LON]],
        left_on="업소ID",
        right_on=schema.SRC_ID,
        how="left",
    )
    top["근거"] = top["근거배지목록"].map(lambda badges: " · ".join(badges))
    display = top[["순위", schema.NAME, schema.CAT_S, schema.ADDR_ROAD, "점수", "근거"]].rename(
        columns={schema.NAME: "상호", schema.CAT_S: "업태", schema.ADDR_ROAD: "주소"}
    )
    st.dataframe(display, width="stretch", hide_index=True)
    st.caption(f"상위 {len(top)}곳 표시 (근거 있는 전체 {len(scored)}곳 중)")

    st.divider()
    st.markdown("#### 지도")
    m = folium.Map(location=[cy, cx], zoom_start=16)
    for _, row in top.dropna(subset=[schema.LAT, schema.LON]).iterrows():
        folium.CircleMarker(
            location=[row[schema.LAT], row[schema.LON]],
            radius=6,
            color=MARKER_COLOR,
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(f"<b>{row[schema.NAME]}</b><br>{row['근거']}", max_width=260),
            tooltip=f"{row['순위']}위 · {row[schema.NAME]}",
        ).add_to(m)
    st_folium(m, height=420, use_container_width=True, key="ranking_map")

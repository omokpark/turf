"""지도 탭 — 주류 가능 업소를 신규🟢·폐업🔴·영업⚪ 색으로, 중심·반경은 지도에서 조작

인허가(MOI) 데이터 기반. 업종 다중필터는 제거하고(영업사원은 술 팔 가능성 있는 곳
전부가 대상), liquor_affinity 임계 토글(전체 주류가능 ≥1 / 주류 중심 ≥2)만 둔다.
수집 안 된 지역은 마커 없이 지도만 나오며, 검색·드래그로 담당구역으로 이동해 쓴다.
"""

import pandas as pd
import streamlit as st

from core import schema
from core.area import Area, MAX_RADIUS_M, MIN_RADIUS_M, filter_radius, walk_minutes
from datasources import moi_store
from signals.outlook import liquor_affinity
from timeline import trend
from ui import channels, data
from ui.map_view import render_map

RECENT_OPEN_DAYS = 90
RECENT_CLOSE_DAYS = 180


def _build_display(roster: pd.DataFrame, cx: float, cy: float, radius: int, affinity_min: int) -> pd.DataFrame:
    """선택 반경 내 주류 가능 업소 + 상태(신규/폐업/영업) 컬럼을 붙여 돌려준다."""
    geo = roster.dropna(subset=[schema.LAT, schema.LON])
    near = filter_radius(geo, Area(cx=cx, cy=cy, radius=radius))
    if len(near) == 0:
        return near.assign(상태=pd.Series(dtype=str))

    affinity = near.apply(lambda r: liquor_affinity(r[schema.CAT_S], r[schema.NAME]), axis=1)
    near = near[affinity >= affinity_min].copy()
    if len(near) == 0:
        return near.assign(상태=pd.Series(dtype=str))

    recent_open_ids = set(trend.recent_openings(near, days=RECENT_OPEN_DAYS)[schema.SRC_ID])
    recent_close_ids = set(trend.recent_closings(near, days=RECENT_CLOSE_DAYS)[schema.SRC_ID])

    def status(row):
        # 최근 폐업만 🔴로 표시하고, 오래전 폐업은 아예 지도에서 뺀다(노이즈 방지).
        if row[schema.IS_OPEN]:
            return "신규" if row[schema.SRC_ID] in recent_open_ids else "영업"
        return "폐업" if row[schema.SRC_ID] in recent_close_ids else None

    near["상태"] = near.apply(status, axis=1)
    return near[near["상태"].notna()].reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def _cached_display(
    cache_key: tuple, cx: float, cy: float, radius: int, affinity_min: int, today: str
) -> pd.DataFrame:
    """_build_display 캐시 래퍼 — rerun(위젯 조작·다른 화면 상호작용)마다 행별
    liquor_affinity 계산이 반복되지 않게 한다. 명부는 DataFrame 해싱을 피하려고
    인자 대신 내부에서 로드하고, cache_key(파티션 목록)·today(신규/폐업 분류 기준일)가
    무효화를 담당한다."""
    return _build_display(data.load_roster(), cx, cy, radius, affinity_min)


def render_map_tab(cx: float, cy: float, radius: int) -> None:
    ctrl_col, walk_col = st.columns([5, 1])
    with ctrl_col:
        st.slider(
            "반경 (m)", min_value=MIN_RADIUS_M, max_value=MAX_RADIUS_M, step=50,
            key="radius_slider", label_visibility="collapsed",
        )
    walk_col.markdown(f"**{radius}m** · 도보 {walk_minutes(radius)}분")

    only_core = st.toggle("주류 중심 업태만 (호프·주점급)", value=False, key="liquor_core_only")
    affinity_min = 2 if only_core else 1

    if len(data.load_roster()) == 0:
        st.info("이 지역은 인허가 데이터가 수집되지 않았습니다 — 지도만 표시됩니다. 담당구역으로 검색·이동하세요.")
        display = None
    else:
        display = _cached_display(
            moi_store.cache_token(), cx, cy, radius, affinity_min,
            pd.Timestamp.today().strftime("%Y-%m-%d"),
        )

    map_data = render_map(radius, display)

    if display is not None:
        n_new = int((display["상태"] == "신규").sum())
        n_close = int((display["상태"] == "폐업").sum())
        st.caption(
            f"주류 가능 업소 {int((display['상태'] != '폐업').sum()):,}곳 · "
            f"🟢 최근 {RECENT_OPEN_DAYS}일 신규 {n_new} · 🔴 최근 {RECENT_CLOSE_DAYS}일 폐업 {n_close}"
        )
    st.caption("🎯 원 끌기 = 중심 이동  ·  ↔️ 가장자리 끌기 = 반경 조절  ·  📌 원 밖 클릭 = 점프  ·  🧭 지도 끌기/줌 = 탐색")

    channels.apply_radius_message(map_data)
    channels.apply_center_click(map_data)

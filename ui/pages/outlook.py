"""구역 동향 탭 — 국면 + 핵심지표 + 최근 신규·폐업 (구 아웃룩 + 변화 통합)

읽는 순서: ① 이 구역은 지금 어떤 국면인가(국면 차트) → ② 왜 그런가(핵심지표) →
③ 지금 뭐가 바뀌고 있나(최근 신규🟢·폐업🔴). 모든 문구는 관측 사실만 (판단 원칙).

반경 정책: 지표·국면은 표본이 얇으면 요동치므로 선택 반경 우선 + 부족 시 담당구역
(800m) 자동 확대(core.area.adaptive_area). 최근 신규·폐업 리스트는 '지금 내 발밑'을
보는 것이라 선택 반경 그대로 쓴다.
"""

import altair as alt
import pandas as pd
import streamlit as st

from core import schema
from core.area import Area, adaptive_area, filter_radius
from datasources import moi_store
from signals.base import AreaContext, IndicatorResult
from signals.outlook import LIQUOR_CATS, LIQUOR_NAME_KEYWORDS, PHASE_BUFFER, current_phase, phase_trajectory
from signals.registry import available_indicators
from timeline import trend
from ui import data
from ui.components.badges import freshness_signal, percentile_signal

# 지표 모듈 import = 레지스트리 등록 (파일 1개 추가 = 카드 1장 추가).
# 영업사원 관점 핵심지표만 유지: 순증 모멘텀·주류친화 전환율·신규 생존율.
# age_mix(업력 구성)는 영업 판단에 약해 제외(2026-07-11), vacancy_recovery는 표본 편차로 제외.
import signals.cohort_survival  # noqa: F401
import signals.liquor_shift  # noqa: F401
import signals.net_momentum  # noqa: F401

# 색: dataviz 검증 통과 쌍 (CVD ΔE 27.6) — 개업=녹색, 폐업=주황. #c0392b는 '주목' 전용.
COLOR_OPEN = "#1a7f5c"
COLOR_CLOSE = "#b3541e"
COLOR_ACCENT = "#c0392b"
COLOR_MUTED = "#9aa5a0"

MIN_SAMPLE = 30  # 이보다 적으면 지표가 노이즈 — adaptive_area가 800m로 넓히는 임계
RECENT_DAYS = 90        # 최근 신규
RECENT_CLOSE_DAYS = 180  # 최근 폐업 — 폐업 신고 지연을 감안해 더 넓게 본다


@st.cache_data(ttl=600, show_spinner=False)
def _cached_indicator_results(
    cache_key: tuple, cx: float, cy: float, eff_radius: int, today: str
) -> dict[str, IndicatorResult]:
    """구역 지표 계산 캐시 — grid_percentile이 기준 명부(수집 자치단체 전체)를
    500m 격자로 잘라 셀마다 재계산하는 것이 rerun마다 반복되지 않게 한다.
    명부는 DataFrame 해싱을 피하려고 인자 대신 내부에서 로드한다."""
    roster = data.load_roster()
    geo = roster.dropna(subset=[schema.LAT, schema.LON])
    area = Area(cx=cx, cy=cy, radius=eff_radius)
    local = filter_radius(geo, area)
    ctx = AreaContext(area=area, establishments=local, rosters={"moi": local}, reference=roster)
    return {ind.id: ind.compute(ctx) for ind in available_indicators({"moi"})}


def render_outlook(cx: float, cy: float, radius: int) -> None:
    freshness = moi_store.freshness()
    roster = data.load_roster()

    if len(roster) == 0:
        st.info(
            "인허가 데이터가 아직 수집되지 않았습니다. 터미널에서 담당 지역을 수집하세요:\n\n"
            "```\npython -m datasources.build_index --district 3220000  # 예: 강남구\n```"
        )
        return

    geo = roster.dropna(subset=[schema.LAT, schema.LON])
    # 지표·국면: 선택 반경 우선, 표본 부족 시 담당구역(800m)으로 자동 확대
    local, eff_radius, widened = adaptive_area(geo, cx, cy, radius, min_sample=MIN_SAMPLE)
    # 최근 신규·폐업 리스트: '지금 내 발밑'이라 선택 반경 그대로
    near = filter_radius(geo, Area(cx=cx, cy=cy, radius=radius))

    st.caption(freshness_signal(freshness) + " · 폐업 신고는 실제보다 수개월 늦게 반영될 수 있음")

    if len(local) < MIN_SAMPLE:
        st.warning(
            f"반경 {eff_radius}m 내 인허가 이력이 {len(local)}건뿐이라 구역 지표를 계산하지 않습니다 "
            f"(최소 {MIN_SAMPLE}건). 수집된 자치단체 안쪽으로 지도를 이동해 보세요."
        )
        _render_recent_lists(near, radius)
        return

    if widened:
        st.info(
            f"선택 반경 {radius}m는 이력이 얇아 **담당구역 {eff_radius}m 기준**으로 국면·지표를 계산합니다 "
            f"(반경 내 이력 {len(local):,}건). 최근 신규·폐업 리스트는 선택 반경 {radius}m 기준입니다."
        )
    else:
        st.caption(f"국면·지표 기준: 반경 {eff_radius}m · 인허가 이력 {len(local):,}건")

    st.markdown(
        "🔴🟠🟡⚪ 아래 배지는 '좋다/나쁘다'가 아니라 **수집 구역 안에서 이 값이 얼마나 "
        "두드러지는지**(통계적 상대 위치)만 나타낸다."
    )
    _render_phase_matrix(local)
    st.divider()
    results_by_id = _cached_indicator_results(
        moi_store.cache_token(), cx, cy, eff_radius, pd.Timestamp.today().strftime("%Y-%m-%d")
    )
    _render_indicator_cards(results_by_id)
    st.divider()
    _render_recent_lists(near, radius)


# ── ③ 최근 신규·폐업 (변화 탭 통합) ────────────────────────────────────────────
def _render_recent_lists(near: pd.DataFrame, radius: int) -> None:
    st.markdown(f"#### 🔄 최근 변화 (선택 반경 {radius}m)")
    if len(near) == 0:
        st.caption("선택 반경 내 인허가 이력이 없습니다.")
        return

    open_col, close_col = st.columns(2)
    with open_col:
        st.markdown(f"**🟢 최근 개업** (최근 {RECENT_DAYS}일 · 방문 골든타임)")
        recent = trend.recent_openings(near, days=RECENT_DAYS)
        if len(recent) == 0:
            st.caption("최근 개업 건이 없습니다.")
        else:
            st.dataframe(
                recent[[schema.NAME, schema.CAT_S, "개업경과일"]].rename(
                    columns={schema.NAME: "상호", schema.CAT_S: "업태", "개업경과일": "경과일"}
                ),
                width="stretch", hide_index=True,
                column_config={
                    "상호": st.column_config.TextColumn(width="medium"),
                    "업태": st.column_config.TextColumn(width="small"),
                    "경과일": st.column_config.NumberColumn(width="small"),
                },
            )
    with close_col:
        st.markdown(f"**🔴 최근 폐업** (최근 {RECENT_CLOSE_DAYS}일 · 자리 회전 예고)")
        closed = trend.recent_closings(near, days=RECENT_CLOSE_DAYS)
        if len(closed) == 0:
            st.caption("최근 폐업 건이 없습니다.")
        else:
            st.dataframe(
                closed[[schema.NAME, schema.CAT_S, "폐업경과일"]].rename(
                    columns={schema.NAME: "상호", schema.CAT_S: "업태", "폐업경과일": "경과일"}
                ),
                width="stretch", hide_index=True,
                column_config={
                    "상호": st.column_config.TextColumn(width="medium"),
                    "업태": st.column_config.TextColumn(width="small"),
                    "경과일": st.column_config.NumberColumn(width="small"),
                },
            )


# ── ① 국면 흐름 (미러 막대) ──────────────────────────────────────────────────
def _render_phase_matrix(local: pd.DataFrame) -> None:
    """연도별 개업(위)·폐업(아래) 미러 막대 + 순증 라인 + 국면 이모지.

    처음엔 개업증감×폐업증감 사분면 산점도였으나 추상 좌표 위 궤적 읽기가 어렵다는
    피드백으로 교체 (2026-07-06) — 시간을 x축에 두는 것이 옳았다.
    """
    traj = phase_trajectory(local, years=6)
    if len(traj) < 2:
        st.info("국면 궤적을 그리기에 연도별 이력이 부족합니다.")
        return

    # 헤드라인 국면은 달력 연도가 아니라 최근 12개월 이동창 — '지금'을 답한다
    now_phase = current_phase(local)
    if now_phase:
        st.markdown(f"#### 🧭 구역 국면 — 최근 12개월 기준 **{now_phase['국면']}**")
        st.caption(
            f"최근 12개월 개업 {now_phase['최근개업']}·폐업 {now_phase['최근폐업']} "
            f"(직전 12개월 {now_phase['직전개업']}·{now_phase['직전폐업']}) · "
            f"±{PHASE_BUFFER:.0%} 안쪽 변화는 '변화 없음'으로 판정 · "
            "아래 차트: 막대 위=개업, 아래=폐업, 선=순증, 상단 이모지=그 해의 국면 (올해는 부분 연도라 제외)"
        )
    else:
        st.markdown("#### 🧭 구역 국면")
        st.caption("막대 위=개업, 아래=폐업, 선=순증. 상단 이모지가 그 해의 국면 (올해는 부분 연도라 제외).")

    # phase_trajectory는 증감·국면까지만 주므로 순증은 여기서 파생
    df = traj.assign(순증=traj["개업"] - traj["폐업"])
    df = df.assign(
        개업표시=df["개업"],  # melt용 별도 컬럼 — id_vars의 "개업"과 겹치면 melt가 조용히 버린다
        폐업표시=-df["폐업"],
        순증라벨=df["순증"].map(lambda v: f"{v:+d}"),
        국면이모지=df["국면"].str.split(" ").str[0],
    )
    top = float(df["개업"].max()) * 1.25  # 국면 이모지 자리
    y_scale = alt.Scale(domain=[float(df["폐업표시"].min()) * 1.15, top * 1.08])
    y_axis = alt.Axis(labelExpr="abs(datum.value)", title="폐업 ↓ 곳 ↑ 개업")
    tooltip = [
        alt.Tooltip("연도:O"),
        alt.Tooltip("개업:Q"),
        alt.Tooltip("폐업:Q"),
        alt.Tooltip("순증:Q"),
        alt.Tooltip("국면:N"),
    ]
    base = alt.Chart(df)

    # 범례용 색 인코딩을 쓰기 위해 개업/폐업을 long 형태로도 준비
    bars_long = df.melt(
        id_vars=["연도", "개업", "폐업", "순증", "국면"], value_vars=["개업표시", "폐업표시"],
        var_name="구분", value_name="표시값",
    )
    bars_long["구분"] = bars_long["구분"].map({"개업표시": "개업", "폐업표시": "폐업"})
    bars = (
        alt.Chart(bars_long)
        .mark_bar(size=28, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("연도:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("표시값:Q", scale=y_scale, axis=y_axis),
            color=alt.Color(
                "구분:N",
                scale=alt.Scale(domain=["개업", "폐업"], range=[COLOR_OPEN, COLOR_CLOSE]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=tooltip,
        )
    )
    zero = alt.Chart(pd.DataFrame({"v": [0]})).mark_rule(color="#d5d9d7").encode(
        y=alt.Y("v:Q", scale=y_scale)
    )
    net_line = base.mark_line(strokeWidth=2, color="#4a4f4d", point=alt.OverlayMarkDef(size=55, color="#4a4f4d")).encode(
        x="연도:O", y=alt.Y("순증:Q", scale=y_scale), tooltip=tooltip
    )
    net_labels = base.mark_text(dy=-14, fontSize=11, color="#4a4f4d").encode(
        x="연도:O", y=alt.Y("순증:Q", scale=y_scale), text="순증라벨:N"
    )
    phase_emoji = base.mark_text(fontSize=16).encode(
        x="연도:O", y=alt.value(14), text="국면이모지:N", tooltip=tooltip
    )
    chart = (bars + zero + net_line + net_labels + phase_emoji).properties(height=340)
    st.altair_chart(chart, width="stretch")


# ── ② 지표 카드 ──────────────────────────────────────────────────────────────
def _render_indicator_cards(results_by_id: dict[str, IndicatorResult]) -> None:
    # 캐시된 결과를 지표 객체(label·fmt)와 다시 짝짓는다 — 등록 순서 유지
    results = [(ind, results_by_id[ind.id]) for ind in available_indicators({"moi"}) if ind.id in results_by_id]

    st.markdown("##### 📊 핵심 지표")
    cols = st.columns(len(results))
    for col, (ind, res) in zip(cols, results):
        with col:
            value_txt = ind.fmt(res.current) if not pd.isna(res.current) else "—"
            delta_txt = None
            if res.previous is not None and not pd.isna(res.current):
                delta_txt = f"직전 {ind.fmt(res.previous)}"
            st.metric(ind.label, value_txt, delta_txt, delta_color="off")
            if res.percentile is not None:
                st.caption(percentile_signal(100 - res.percentile))

    for ind, res in results:
        with st.expander(f"{ind.label} — 근거·추이"):
            st.write(res.fact)
            if ind.id == "liquor_shift":
                # '주류친화 전환율'이 모호하다는 피드백(2026-07-11) — 어떤 업태가 포함되는지 노출
                st.caption(
                    "**주류친화 업태**: " + ", ".join(sorted(LIQUOR_CATS))
                    + " + 상호에 " + "·".join(LIQUOR_NAME_KEYWORDS) + " 포함"
                    + " · 휴게음식점 인허가(주류 판매 불가)는 제외"
                )
            if res.series is not None and len(res.series) > 0:
                st.altair_chart(_series_chart(ind.id, res.series), width="stretch")


def _series_chart(indicator_id: str, series: pd.DataFrame) -> alt.Chart:
    """지표별 시계열 차트. 2계열(개업/폐업)만 범례, 단일 계열은 제목이 이름."""
    if indicator_id == "net_momentum":
        long = series.melt(id_vars="월", value_vars=["개업", "폐업"], var_name="구분", value_name="건수")
        return (
            alt.Chart(long)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("월:O", axis=alt.Axis(labelAngle=-45, values=list(series["월"][::6]))),
                y=alt.Y("건수:Q"),
                color=alt.Color(
                    "구분:N",
                    scale=alt.Scale(domain=["개업", "폐업"], range=[COLOR_OPEN, COLOR_CLOSE]),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=["월:O", "구분:N", "건수:Q"],
            )
            .properties(height=200)
        )
    if indicator_id == "vacancy_recovery":
        return (
            alt.Chart(series)
            .mark_bar(color=COLOR_OPEN, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=18)
            .encode(
                x=alt.X("연도:O", title="폐업 연도"),
                y=alt.Y("중앙값공백일수:Q", title="중앙값 공백일수 (24개월 내 재입점 건)"),
                tooltip=[
                    "연도:O",
                    alt.Tooltip("중앙값공백일수:Q", title="중앙값(일)"),
                    alt.Tooltip("재입점률:Q", title="재입점률(%)"),
                    alt.Tooltip("완결폐업수:Q", title="완결 폐업 수"),
                ],
            )
            .properties(height=200)
        )
    if indicator_id == "cohort_survival":
        line = (
            alt.Chart(series)
            .mark_line(strokeWidth=2, color=COLOR_OPEN, point=alt.OverlayMarkDef(size=70, color=COLOR_OPEN))
            .encode(
                x=alt.X("코호트연도:O", title="개업 연도"),
                y=alt.Y("생존율:Q", title="1년 생존율(%)", scale=alt.Scale(domain=[0, 100])),
                tooltip=["코호트연도:O", "생존율:Q", "코호트크기:Q"],
            )
        )
        labels = (
            alt.Chart(series)
            .mark_text(dy=-12, fontSize=11, color="#4a4f4d")
            .encode(x="코호트연도:O", y="생존율:Q", text=alt.Text("생존율:Q", format=".0f"))
        )
        return (line + labels).properties(height=200)
    if indicator_id == "liquor_shift":
        return (
            alt.Chart(series)
            .mark_line(strokeWidth=2, color=COLOR_CLOSE, point=alt.OverlayMarkDef(size=70, color=COLOR_CLOSE))
            .encode(
                x=alt.X("연도:O"),
                y=alt.Y("주류친화비중:Q", title="신규 개업 중 주류친화(%)"),
                tooltip=["연도:O", "주류친화비중:Q", "개업수:Q"],
            )
            .properties(height=200)
        )
    if indicator_id == "age_mix":
        return (
            alt.Chart(series)
            .mark_bar(color=COLOR_OPEN, cornerRadiusEnd=4, size=18)
            .encode(
                x=alt.X("업소수:Q"),
                y=alt.Y("업력구간:N", sort=None, title=None),
                tooltip=["업력구간:N", "업소수:Q"],
            )
            .properties(height=170)
        )
    # 새 지표가 전용 차트 없이 추가돼도 죽지 않게 — 표로 폴백
    return alt.Chart(series).mark_point()

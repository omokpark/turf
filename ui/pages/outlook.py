"""M0 구역 아웃룩 탭 — 국면 매트릭스 + 지표 카드 5개

읽는 순서 그대로 배치한다: ① 이 구역은 지금 어떤 국면인가(매트릭스)
→ ② 왜 그런가(지표 카드·시계열). 모든 문구는 관측 사실만 (판단 원칙).
"""

import altair as alt
import pandas as pd
import streamlit as st

from core import schema
from core.area import Area, OUTLOOK_RADIUS_M, filter_radius
from datasources import moi_store
from signals.base import AreaContext
from signals.outlook import phase_trajectory
from signals.registry import available_indicators

# 지표 모듈 import = 레지스트리 등록 (파일 1개 추가 = 카드 1장 추가)
import signals.age_mix  # noqa: F401
import signals.cohort_survival  # noqa: F401
import signals.liquor_shift  # noqa: F401
import signals.net_momentum  # noqa: F401
# vacancy_recovery(공실 회복 속도)는 제외 — 연도별 재입점 표본이 적어 중앙값 편차가
# 너무 큼 (2026-07-06 사용자 결정). 주소키가 건물 단위로 정교해지는 Phase 5에서 재평가.

# 색: dataviz 검증 통과 쌍 (CVD ΔE 27.6) — 개업=녹색, 폐업=주황. #c0392b는 '주목' 전용.
COLOR_OPEN = "#1a7f5c"
COLOR_CLOSE = "#b3541e"
COLOR_ACCENT = "#c0392b"
COLOR_MUTED = "#9aa5a0"

MIN_SAMPLE = 30  # 이보다 적으면 지표가 노이즈 — 계산하지 않고 이유를 밝힌다


@st.cache_data(ttl=600, show_spinner=False)
def _load_roster(cache_key: tuple) -> pd.DataFrame:
    """파티션 전체 로드. cache_key = 파일목록+수정시각 — 파티션 추가·재수집 시 자동 무효화."""
    return moi_store.load_roster()


def render_outlook(cx: float, cy: float) -> None:
    freshness = moi_store.freshness()
    roster = _load_roster(moi_store.cache_token())

    if len(roster) == 0:
        st.info(
            "인허가 데이터가 아직 수집되지 않았습니다. 터미널에서 담당 지역을 수집하세요:\n\n"
            "```\npython -m datasources.build_index --district 3220000  # 예: 강남구\n```"
        )
        return

    area = Area(cx=cx, cy=cy, radius=OUTLOOK_RADIUS_M)
    local = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]), area)

    summary = moi_store.cached_summary()
    st.caption(
        f"기준: 중심 반경 {OUTLOOK_RADIUS_M}m · 인허가 이력 {len(local):,}건 "
        f"(보유 데이터: {', '.join(summary['업종'] + ' ' + summary['행수'].map('{:,}'.format) + '건')}) · "
        f"수집 시점 {freshness:%Y-%m-%d %H:%M} · 폐업 신고는 실제보다 수개월 늦게 반영될 수 있음"
    )

    if len(local) < MIN_SAMPLE:
        st.warning(
            f"반경 {OUTLOOK_RADIUS_M}m 내 인허가 이력이 {len(local)}건뿐이라 구역 지표를 계산하지 않습니다 "
            f"(최소 {MIN_SAMPLE}건). 수집된 자치단체 안쪽으로 지도를 이동해 보세요."
        )
        return

    ctx = AreaContext(area=area, establishments=local, rosters={"moi": local}, reference=roster)

    _render_phase_matrix(local, ctx)
    st.divider()
    _render_indicator_cards(ctx)


# ── ① 국면 흐름 (미러 막대) ──────────────────────────────────────────────────
def _render_phase_matrix(local: pd.DataFrame, ctx: AreaContext) -> None:
    """연도별 개업(위)·폐업(아래) 미러 막대 + 순증 라인 + 국면 이모지.

    처음엔 개업증감×폐업증감 사분면 산점도였으나 추상 좌표 위 궤적 읽기가 어렵다는
    피드백으로 교체 (2026-07-06) — 시간을 x축에 두는 것이 옳았다.
    """
    traj = phase_trajectory(local, years=6, today=ctx.now)
    if len(traj) < 2:
        st.info("국면 궤적을 그리기에 연도별 이력이 부족합니다.")
        return

    latest = traj.iloc[-1]
    st.markdown(f"#### 구역 국면 — {int(latest['연도'])}년 기준 **{latest['국면']}**")
    st.caption("막대 위=개업, 아래=폐업, 선=순증. 상단 이모지가 그 해의 국면 (올해는 부분 연도라 제외).")

    # phase_trajectory는 증감·국면까지만 주므로 순증은 여기서 파생
    df = traj.assign(순증=traj["개업"] - traj["폐업"])
    df = df.assign(
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
        id_vars=["연도", "개업", "폐업", "순증", "국면"], value_vars=["개업", "폐업표시"],
        var_name="구분", value_name="표시값",
    )
    bars_long["구분"] = bars_long["구분"].map({"개업": "개업", "폐업표시": "폐업"})
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
def _render_indicator_cards(ctx: AreaContext) -> None:
    indicators = available_indicators({"moi"})
    results = [(ind, ind.compute(ctx)) for ind in indicators]

    cols = st.columns(len(results))
    for col, (ind, res) in zip(cols, results):
        with col:
            value_txt = ind.fmt(res.current) if not pd.isna(res.current) else "—"
            delta_txt = None
            if res.previous is not None and not pd.isna(res.current):
                delta_txt = f"직전 {ind.fmt(res.previous)}"
            st.metric(ind.label, value_txt, delta_txt, delta_color="off")
            if res.percentile is not None:
                st.caption(f"수집 구역 내 상위 {100 - res.percentile:.0f}% 수준")

    for ind, res in results:
        with st.expander(f"{ind.label} — 근거·추이"):
            st.write(res.fact)
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

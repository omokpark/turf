"""'방문 우선순위' 탭 — 가용 신호를 스코어러로 합산해 근거 배지와 함께 랭킹으로 보여준다.

판단 원칙: 점수는 항상 근거 배지와 함께 나온다 (Scorer 계약이 강제). 추천·예측
문구는 쓰지 않는다. 구역 아웃룩의 국면은 랭킹 위에 맥락으로만 병기한다 — 개별 업소의
근거가 아니라 "이 구역 전체가 지금 어떤 판인가"라는 별도 정보이기 때문이다.

피드백 2채널 (2026-07-12 설계): 카드마다 👍 방문가치 높았음/👎 없었음(그 순간의
신호값·점수 스냅샷과 함께 저장, 추후 배지별 lift 분석·가중치 조정용)과 별도로,
"⋯" 안에 업소 사유(폐업/주류미취급/당사 우호 업소/기타) — 업소 자체의 사실이라 랭킹
품질 피드백과 절대 섞이지 않는다(섞이면 "우호 업소라 없었음"이 학습돼 최고의 개척
후보를 피하게 된다).
노출 로그(feedback_store.log_exposure)는 피드백 유무와 무관하게 상위 30곳을
기록해, 나중에 "피드백군 vs 노출 전체"의 대조군 역할을 한다.
"""

import html

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core import schema
from core.area import Area, OUTLOOK_RADIUS_M, filter_radius
from datasources import feedback_store, moi_store, naver, places, places_quota, seoul
from datasources.places_quota import QuotaExceeded
from scorers.base import available_scorers, validate_score_result
from signals import base as signal_base
from signals.base import AreaContext
from signals.outlook import current_phase, liquor_affinity
from signals.registry import available_signals
from ui import chat_context, data
from ui.chatbot import render_chat
from ui.components.badges import quota_signal, render_badges
from ui.components.csv_export import neutralize_formulas

# 신호·스코어러 모듈 import = 레지스트리 등록 (파일 1개 추가 = 랭킹에 자동 반영)
import signals.buzz_momentum  # noqa: F401
import signals.conversion_vector  # noqa: F401
import signals.franchise  # noqa: F401
import signals.growth_momentum  # noqa: F401
import signals.liquor_adjacency  # noqa: F401
import signals.night_index  # noqa: F401
import signals.recent_opening  # noqa: F401
import signals.review_momentum  # noqa: F401
import signals.star_level  # noqa: F401
import signals.survivor  # noqa: F401
import scorers.destination_index  # noqa: F401
import scorers.known_star  # noqa: F401
import scorers.weighted_sum  # noqa: F401

TOP_N = 30
SNAPSHOT_TOP_N = 10  # Enterprise 쿼터(월 900캡)는 최상위에만 — 나머지는 Pro 폐업검증만
MARKER_COLOR = "#c0392b"
RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


@st.cache_data(ttl=3600, show_spinner=False)
def _google_verification(shops: tuple) -> tuple[dict, list[str]]:
    """상위 후보를 구글 Places로 교차검증 — 2패스 비용 설계의 실행부.

    shops: (순위인덱스, 업소ID, 상호, 도로명, 지번, 위도, 경도) 튜플들 — st.cache_data
    키로 해시 가능해야 해서 DataFrame 대신 원시 튜플을 받는다. 캐시 덕에 rerun마다
    30곳 × 파일 캐시 순회가 반복되지 않는다 (HTTP 자체는 places.py의 30일 캐시가 방어).

    상위 SNAPSHOT_TOP_N곳: 평판 스냅샷(Enterprise — 평점·리뷰수·심야영업·폐업).
    나머지 TOP_N까지: 폐업 검증만(Pro — 헛걸음 제거). place_id 검색은 무제한 무료.
    쿼터 한도 도달 시 해당 등급만 생략하고 계속한다 (30일 캐시 히트는 쿼터 소비 0).
    반환: (업소ID → 배지 리스트, 사용자 안내 문구 리스트)
    """
    extra: dict = {}
    notes: list[str] = []
    enterprise_blocked = False
    pro_blocked = False
    for i, est_id, name, road, jibun, lat, lon in shops:
        token = naver.address_token(road, jibun)
        try:
            pid = places.find_place_id(name, token, lat, lon)
        except Exception:
            continue  # ID 검색 실패는 배지 없이 넘어간다
        if not pid:
            continue
        badges: list[str] = []
        if i < SNAPSHOT_TOP_N and not enterprise_blocked:
            try:
                badges = places.snapshot_badges(places.place_snapshot(pid))
            except QuotaExceeded as e:
                enterprise_blocked = True
                notes.append(str(e))
        if not badges and not pro_blocked:  # 스냅샷을 못 받았으면 폐업 검증이라도
            try:
                b = places.status_badge(places.business_status(pid))
                badges = [b] if b else []
            except QuotaExceeded as e:
                pro_blocked = True
                notes.append(str(e))
        if badges:
            extra[est_id] = badges
        if enterprise_blocked and pro_blocked:
            break
    return extra, notes


@st.cache_data(ttl=600, show_spinner=False)
def _cached_signal_results(
    cache_key: tuple, cx: float, cy: float, radius: int, providers: tuple, today: str
) -> dict[str, pd.DataFrame]:
    """가용 신호 전체의 계산 결과 캐시 — rerun(위젯 조작, 이후 챗봇 메시지)마다
    O(n²) 이웃 루프 3개와 Naver 파일 캐시 전수 순회가 반복되지 않게 한다.

    명부는 DataFrame 해싱을 피하려고 인자 대신 내부에서 로드한다. 무효화 키:
    cache_key(파티션 목록·수정시각) + 좌표·반경 + providers + today(신호가 경과일
    기반이라 날짜가 바뀌면 재계산).
    """
    roster = data.load_roster()
    area = Area(cx=cx, cy=cy, radius=radius)
    local = filter_radius(roster.dropna(subset=[schema.LAT, schema.LON]), area)
    ctx = AreaContext(area=area, establishments=local, rosters={"moi": local}, reference=roster)
    results: dict[str, pd.DataFrame] = {}
    for sig in available_signals(set(providers)):
        result = sig.compute(ctx)
        if len(result) > 0:
            results[sig.id] = result
    return results


def render_ranking(cx: float, cy: float, radius: int) -> None:
    roster = data.load_roster()
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
    now_phase = current_phase(outlook_local)
    if now_phase:
        st.caption(
            f"구역 국면(반경 {OUTLOOK_RADIUS_M}m·최근 12개월 기준, 참고용 맥락): **{now_phase['국면']}**"
        )

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
        captions=[s.caption for s in scorers_avail],
        horizontal=True,
        key="ranking_scorer",
    )

    spinner_msg = "신호 계산 중..."
    if "naver" in providers:
        spinner_msg = "신호 계산 중... (블로그 조회는 처음 한 번만 느리고 7일간 캐시됩니다)"
    with st.spinner(spinner_msg):
        signal_results = _cached_signal_results(
            moi_store.cache_token(), cx, cy, radius,
            tuple(sorted(providers)), ctx.now.strftime("%Y-%m-%d"),
        )
        scored = scorer.score(signal_results, ctx)
    validate_score_result(scored)

    # 주류 판매 불가 업소(휴게음식점 등 affinity 0 — 카페·패스트푸드류)는 방문 영업
    # 대상이 아니다 — 지도 탭과 같은 기준으로 랭킹에서 제외하고 순위를 다시 매긴다.
    # (신호·밀집도 계산에는 포함 — 유동 프록시·전환 벡터의 모수는 전 업소가 맞다.)
    aff = local.apply(
        lambda r: liquor_affinity(r[schema.CAT_S], r[schema.NAME], r[schema.CAT_L]), axis=1
    )
    sellable = set(local.loc[aff.values >= 1, schema.SRC_ID])
    n_before = len(scored)
    scored = scored[scored["업소ID"].isin(sellable)].reset_index(drop=True)
    scored["순위"] = scored.index + 1
    n_excluded = n_before - len(scored)

    if len(scored) == 0:
        st.info("근거를 만들 수 있는 업소가 없습니다.")
        return

    st.caption(f"{scorer.label} — {scorer.description}")

    merge_cols = [schema.SRC_ID, schema.NAME, schema.CAT_S, schema.ADDR_ROAD, schema.ADDR_JIBUN, schema.LAT, schema.LON]
    top = scored.head(TOP_N).merge(local[merge_cols], left_on="업소ID", right_on=schema.SRC_ID, how="left")
    # 31위 이하 — 카드로는 안 보이지만 근거는 있는 나머지. 챗봇 컨텍스트 전용(Google 교차검증 없음).
    rest = scored[scored["순위"] > TOP_N].merge(local[merge_cols], left_on="업소ID", right_on=schema.SRC_ID, how="left")

    # Places 키가 있으면 상위 후보를 구글로 교차검증 (2패스 — 첫 조회만 느리고 30일 캐시)
    if places.available():
        quota_line = quota_signal(places_quota.summary())
        if quota_line:
            st.caption(f"Google Places 월 쿼터 — {quota_line}")
        shops = tuple(
            (i, row["업소ID"], row[schema.NAME], row[schema.ADDR_ROAD], row[schema.ADDR_JIBUN],
             float(row[schema.LAT]), float(row[schema.LON]))
            for i, (_, row) in enumerate(top.iterrows())
            if pd.notna(row[schema.LAT]) and pd.notna(row[schema.LON])
        )
        with st.spinner("구글 Places 교차검증 중... (첫 조회만 느리고 30일간 캐시됩니다)"):
            google_badges, quota_notes = _google_verification(shops)
        top["근거배지목록"] = top.apply(
            lambda r: list(r["근거배지목록"]) + google_badges.get(r["업소ID"], []), axis=1
        )
        for note in quota_notes:
            st.caption(f"ℹ️ {note}")

    top["근거"] = top["근거배지목록"].map(lambda badges: " · ".join(badges))

    # 신호값 스냅샷 준비 — 업소별로 set_index를 반복하지 않도록 한 번만 인덱싱
    indexed_signals = {sig_id: df.set_index(signal_base.EST_ID) for sig_id, df in signal_results.items()}

    # 노출 로그: 피드백이 없어도 "무엇이 노출됐는지"가 있어야 배지별 lift(피드백군 vs
    # 노출 전체)를 나중에 계산할 수 있다 — 같은 (날짜·구역·스코어러)는 최신 것으로 덮어쓴다.
    exposure_rows = [
        {
            "순위": int(row["순위"]), "업소ID": row["업소ID"], "상호": row[schema.NAME],
            "점수": float(row["점수"]),
            "신호값": feedback_store.signal_snapshot(indexed_signals, row["업소ID"]),
            "배지": row["근거배지목록"],
        }
        for _, row in top.iterrows()
    ]
    feedback_store.log_exposure(scorer.id, cx, cy, radius, exposure_rows)

    fb_state = feedback_store.latest_feedback()
    attr_state = feedback_store.latest_attributes()

    excluded_note = f" · 주류 판매 불가 업소 {n_excluded}곳 제외" if n_excluded else ""
    st.markdown(f"##### 📋 상위 {len(top)}곳 (근거 있는 전체 {len(scored)}곳 중{excluded_note})")
    for _, row in top.iterrows():
        rank = int(row["순위"])
        est_id = row["업소ID"]
        medal = RANK_MEDALS.get(rank, f"{rank}위")
        with st.container(border=True):
            head_col, score_col = st.columns([4, 1])
            with head_col:
                # unsafe_allow_html을 안 쓰므로 st.markdown이 상호명 안의 HTML 특수문자를
                # 자동으로 이스케이프한다 (외부 데이터라 반드시 이 경로를 유지할 것).
                st.markdown(f"{medal} **{row[schema.NAME]}** · {row[schema.CAT_S]}")
                st.caption(row[schema.ADDR_ROAD] or "주소 정보 없음")
            with score_col:
                score = min(1.0, max(0.0, float(row["점수"])))
                st.progress(score, text=f"{score:.2f}")
            render_badges(row["근거배지목록"])

            shop_attrs = attr_state.get(est_id, {})
            attr_chips = [
                feedback_store.ATTRIBUTE_CHIP_LABELS[attr]
                for attr in feedback_store.ATTRIBUTE_LABELS
                if shop_attrs.get(attr)
            ]
            if attr_chips:
                render_badges(attr_chips)

            current_label = fb_state.get(est_id, {}).get("라벨")
            up_col, down_col, more_col = st.columns([2, 2, 1])
            with up_col:
                if st.button(
                    "👍 방문가치 높았음", key=f"fb_up_{rank}_{est_id}", use_container_width=True,
                    type="primary" if current_label == feedback_store.LABEL_UP else "secondary",
                ):
                    feedback_store.record_feedback(
                        est_id, row[schema.NAME], feedback_store.LABEL_UP, scorer.id,
                        cx, cy, radius, float(row["점수"]), row["근거배지목록"],
                        feedback_store.signal_snapshot(indexed_signals, est_id),
                    )
                    st.toast(f"👍 {row[schema.NAME]} — 방문가치 높았음으로 기록했습니다.")
                    st.rerun()
            with down_col:
                if st.button(
                    "👎 방문가치 없었음", key=f"fb_down_{rank}_{est_id}", use_container_width=True,
                    type="primary" if current_label == feedback_store.LABEL_DOWN else "secondary",
                ):
                    feedback_store.record_feedback(
                        est_id, row[schema.NAME], feedback_store.LABEL_DOWN, scorer.id,
                        cx, cy, radius, float(row["점수"]), row["근거배지목록"],
                        feedback_store.signal_snapshot(indexed_signals, est_id),
                    )
                    st.toast(f"👎 {row[schema.NAME]} — 방문가치 없었음으로 기록했습니다.")
                    st.rerun()
            with more_col:
                with st.popover("⋯", use_container_width=True):
                    # 방문가치 피드백과 분리된 사실 정정 채널 — 여기서 기록하는 폐업/주류미취급/
                    # 기타는 업소 자체의 사실이지 랭킹 품질 신호가 아니다(섞으면 학습이 오염된다).
                    st.caption("업소 사유 (방문가치 👍/👎와 별개로 기록)")
                    for attr, label in feedback_store.ATTRIBUTE_LABELS.items():
                        cur = shop_attrs.get(attr, False)
                        new = st.checkbox(label, value=cur, key=f"attr_{attr}_{rank}_{est_id}")
                        if new != cur:
                            feedback_store.record_attribute(est_id, row[schema.NAME], attr, new)
                            st.rerun()

    # 방문 리스트 CSV — 상위 N곳 + 근거 (업종 구성 탭에 있던 내보내기를 여기로 흡수)
    export = top[["순위", schema.NAME, schema.CAT_S, schema.ADDR_ROAD, "점수", "근거"]].rename(
        columns={schema.NAME: "상호", schema.CAT_S: "업태", schema.ADDR_ROAD: "주소"}
    )
    st.download_button(
        "⬇️ 방문 리스트 CSV 다운로드",
        neutralize_formulas(export).to_csv(index=False).encode("utf-8-sig"),
        file_name="turf_방문우선순위.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown("#### 🗺️ 지도")
    m = folium.Map(location=[cy, cx], zoom_start=16)
    for _, row in top.dropna(subset=[schema.LAT, schema.LON]).iterrows():
        # 상호명·근거 배지는 외부 데이터(인허가 등록 상호, Naver 블로그 텍스트 등)라
        # HTML로 그대로 넣으면 저장형 XSS가 된다 — 반드시 escape 후 삽입한다.
        shop_name = html.escape(str(row[schema.NAME]))
        reason = html.escape(str(row["근거"]))
        folium.CircleMarker(
            location=[row[schema.LAT], row[schema.LON]],
            radius=6,
            color=MARKER_COLOR,
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(f"<b>{shop_name}</b><br>{reason}", max_width=260),
            tooltip=folium.Tooltip(f"{row['순위']}위 · {shop_name}", permanent=False, direction="top", sticky=False),
        ).add_to(m)
    st_folium(m, height=420, use_container_width=True, key="ranking_map")

    render_chat(
        "ranking",
        chat_context.ranking_context(top, rest, scorer, now_phase, n_excluded, radius, indexed_signals),
    )

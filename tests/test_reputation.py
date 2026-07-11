"""Phase 4 평판 축 — 주소 토큰·M8 버즈·리뷰 모멘텀·목적지 지수 (Naver는 monkeypatch)"""

import pandas as pd
import pytest

from core import schema
from core.area import Area
from datasources import naver
from scorers import base as scorer_base
from scorers.destination_index import DestinationIndex
from scorers.known_star import KnownStar
from signals import base as signal_base
from signals.base import AreaContext
from signals.buzz_momentum import BuzzMomentum
from signals.review_momentum import ReviewMomentum
from signals.star_level import StarLevel
from tests.conftest import make_roster

TODAY = pd.Timestamp("2026-07-06")


def _ctx(df):
    return AreaContext(
        area=Area(cx=127.0276, cy=37.4979, radius=400),
        establishments=df,
        rosters={"moi": df},
        today=TODAY,
    )


# ── 주소 토큰 (동명 업소 오매칭 방어) ──────────────────────────────────────────
def test_address_token_prefers_dong_then_road_then_gu():
    assert naver.address_token("서울 강남구 테헤란로 129", "서울 강남구 역삼동 736") == "역삼동"
    assert naver.address_token("서울 강남구 테헤란로 129", "") == "테헤란로"
    assert naver.address_token("서울 강남구 129", None) == "강남구"
    assert naver.address_token(None, None) == ""


# ── M8 버즈 모멘텀 — 골든타임 업소만 조회 (쿼터 방어) ─────────────────────────
def test_buzz_momentum_queries_only_golden_window(monkeypatch):
    queried = []

    def fake_posts(name, token, since):
        queried.append(name)
        return 7, pd.Timestamp("2026-07-01")

    monkeypatch.setattr(naver, "blog_posts_since", fake_posts)
    df = make_roster(
        [
            {schema.NAME: "신상집", schema.LICENSED_AT: "2026-06-01"},   # 골든타임 (35일차)
            {schema.NAME: "장수집", schema.LICENSED_AT: "2015-03-01"},   # 창 밖 — 조회하면 안 됨
        ]
    )
    result = BuzzMomentum().compute(_ctx(df))
    signal_base.validate_signal_result(result)
    assert queried == ["신상집"]  # 장수집은 Naver 호출 자체가 없어야 한다
    row = result.iloc[0]
    assert row[signal_base.RAW] == 7
    assert "개업 35일차에 블로그 7건" in row[signal_base.BADGE]


# ── 리뷰 모멘텀 — R = log(1+블로그)/업력, 백분위 VALUE ────────────────────────
def test_review_momentum_rewards_fast_buzz_over_old_accumulation(monkeypatch):
    posts_by_name = {"신흥강자": 20, "오래된집": 20, "무명집": 0}
    monkeypatch.setattr(
        naver, "blog_posts_since", lambda name, token, since: (posts_by_name[name], None)
    )
    df = make_roster(
        [
            {schema.NAME: "신흥강자", schema.LICENSED_AT: "2025-07-01"},  # 업력 1년, 20건
            {schema.NAME: "오래된집", schema.LICENSED_AT: "2016-07-01"},  # 업력 10년, 20건
            {schema.NAME: "무명집", schema.LICENSED_AT: "2020-01-01"},    # 0건
        ]
    )
    result = ReviewMomentum().compute(_ctx(df)).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}
    # 같은 20건이라도 업력 1년이 10년보다 R가 높아야 한다 (모멘텀이지 누적량이 아님)
    assert result.loc[ids["신흥강자"], signal_base.RAW] > result.loc[ids["오래된집"], signal_base.RAW]
    assert result.loc[ids["무명집"], signal_base.RAW] == 0.0
    assert pd.isna(result.loc[ids["무명집"], signal_base.BADGE])


# ── 목적지 지수 — 저밀집에서 리뷰 붙는 집이 위로 ──────────────────────────────
def test_destination_index_excludes_unobserved_and_ranks_by_ratio(monkeypatch):
    # 번화가 이웃은 블로그가 많고(기대치 높음), 골목 이웃은 적다(기대치 낮음).
    # 같은 15건이라도 골목에서의 15건이 기대치 초과 폭이 커야 한다 — 목적지 지수의 핵심.
    posts_by_name = {"골목의보석": 15, "번화가평범": 15, "무명집": 0}
    monkeypatch.setattr(
        naver,
        "blog_posts_since",
        lambda name, token, since: (
            posts_by_name.get(name, 30 if name.startswith("번화가이웃") else 1),
            None,
        ),
    )
    rows = [
        # 저밀집 골목 — 중심에서 ≈350m 동쪽. 밀집도 반경(300m) 밖이어야 번화가와 다른
        # 밀집 코호트로 분리된다 (원래 ≈250m였는데 반경 안이라 전부 한 코호트로 묶여
        # 순위 검증이 동점 정렬 안정성으로만 통과하고 있었음 — Day 14 발견·수정)
        {schema.NAME: "골목의보석", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0316,
         schema.LICENSED_AT: "2024-07-01"},
        # 고밀집 번화가: 같은 좌표에 이웃 다수
        {schema.NAME: "번화가평범", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0276,
         schema.LICENSED_AT: "2024-07-01"},
        {schema.NAME: "무명집", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0276,
         schema.LICENSED_AT: "2020-01-01"},
    ]
    for i in range(10):  # 번화가 이웃 — 밀집도·기대치 모두 높음
        rows.append({schema.NAME: f"번화가이웃{i}", schema.CAT_S: "한식", schema.LAT: 37.4979,
                     schema.LON: 127.0276, schema.LICENSED_AT: "2024-01-01"})
    for i in range(5):  # 골목 이웃 — 저밀집 코호트 형성, 블로그 드묾
        rows.append({schema.NAME: f"골목이웃{i}", schema.CAT_S: "한식", schema.LAT: 37.4979,
                     schema.LON: 127.0316, schema.LICENSED_AT: "2024-01-01"})
    df = make_roster(rows)
    ctx = _ctx(df)

    review = ReviewMomentum().compute(ctx)
    scored = DestinationIndex().score({"review_momentum": review}, ctx)
    scorer_base.validate_score_result(scored)

    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}
    assert ids["무명집"] not in set(scored[scorer_base.EST_ID])  # 블로그 미관측 — 제외
    ranks = scored.set_index(scorer_base.EST_ID)[scorer_base.RANK]
    assert ranks[ids["골목의보석"]] < ranks[ids["번화가평범"]]  # 저밀집의 같은 관측량이 위

    # "기대치의 N배"의 근거(어느 코호트 평균인지)가 배지에 병기돼야 한다.
    # 골목 코호트 = 골목의보석 + 골목이웃 5 = 한식 6곳 (MIN_COHORT 충족 → 코호트 기대치)
    badges = scored.set_index(scorer_base.EST_ID)[scorer_base.BADGES]
    gem_badge = badges[ids["골목의보석"]][0]
    assert "기대치 = 같은 구간 한식 6곳 평균" in gem_badge


def test_destination_index_badge_flags_expectation_floor(monkeypatch):
    # 비교군(코호트) 평균 R가 바닥값(E_FLOOR) 미만이면 배수의 분모가 바닥값으로 바뀐다 —
    # 그 사실과 '표시 배수는 하한값'임이 배지에 드러나야 한다.
    posts = {"조용한동네보석": 2}  # 업력 10년·블로그 2건 → R≈0.11, 이웃은 전부 0건
    monkeypatch.setattr(
        naver, "blog_posts_since", lambda name, token, since: (posts.get(name, 0), None)
    )
    rows = [{schema.NAME: "조용한동네보석", schema.LICENSED_AT: "2016-07-01"}]
    for i in range(5):  # 같은 업태·같은 밀집도 이웃 — 코호트 평균 ≈ 0.11/6 < 0.05
        rows.append({schema.NAME: f"조용한이웃{i}", schema.LICENSED_AT: "2016-01-01"})
    df = make_roster(rows)
    ctx = _ctx(df)

    review = ReviewMomentum().compute(ctx)
    scored = DestinationIndex().score({"review_momentum": review}, ctx)
    scorer_base.validate_score_result(scored)

    assert len(scored) == 1  # 블로그 관측은 보석 1곳뿐
    badge = scored.iloc[0][scorer_base.BADGES][0]
    assert "바닥값" in badge and "하한값" in badge


def test_destination_index_empty_without_review_signal():
    df = make_roster([{schema.NAME: "아무집"}])
    scored = DestinationIndex().score({}, _ctx(df))
    assert len(scored) == 0

# ── 알려진 스타 — 게재 속도(규모 축) 판정, 증분은 배지의 변곡 정보 ──────────────
def test_star_level_cap_regime_uses_span_and_omits_trend(monkeypatch):
    # 진짜 스타: 최신 100건이 50일에 몰림(API 캡) → 날짜 범위 기준 속도 100/50 = 월 60건.
    # 직전 창은 잘려서 과소집계 — 증감 배지는 생략돼야 한다(가짜 급증 방지).
    dates_by_name = {
        "스타집": [TODAY] * 99 + [TODAY - pd.Timedelta(days=50)],
        "평범집": [TODAY - pd.Timedelta(days=d) for d in (10, 60, 150)],
        # 증감이 관측되는(float) 업소를 섞는다 — _증감 컬럼이 float dtype이 되면서
        # 캡 업소의 None이 NaN으로 변해 "+nan%"가 새던 회귀의 재현 조건
        "성장집": [TODAY - pd.Timedelta(days=i * 2) for i in range(40)]
        + [TODAY - pd.Timedelta(days=95 + i * 4) for i in range(20)],
    }
    monkeypatch.setattr(naver, "blog_post_dates", lambda name, token: dates_by_name.get(name, []))
    df = make_roster([{schema.NAME: "스타집"}, {schema.NAME: "평범집"}, {schema.NAME: "성장집"}])
    ctx = _ctx(df)

    result = StarLevel().compute(ctx).set_index(signal_base.EST_ID)
    signal_base.validate_signal_result(result.reset_index())

    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}
    star_badge = result.loc[ids["스타집"], signal_base.BADGE]
    assert "월 60.0건" in star_badge
    assert "직전" not in star_badge  # 캡 왜곡 — 증감 생략
    assert "nan" not in star_badge   # None→NaN 혼입 시 "+nan%"로 새는 회귀 방지
    assert result.loc[ids["스타집"], signal_base.RAW] == 60.0  # 건/월
    assert pd.isna(result.loc[ids["평범집"], signal_base.BADGE])  # 상위 20% 밖

    scored = KnownStar().score({"star_level": result.reset_index()}, ctx)
    scorer_base.validate_score_result(scored)
    assert list(scored[scorer_base.EST_ID]) == [ids["스타집"]]  # 배지(스타 판정) 업소만 랭킹


def test_star_level_trend_badge_and_dead_star_excluded(monkeypatch):
    # 비캡 구간: 최근 90일 20건 vs 직전 90일 10건 → +100% 증감이 배지에 병기.
    # 죽은 스타(전부 180일 밖 게시)는 속도 0 — 배지도 랭킹도 없어야 한다.
    surge = [TODAY - pd.Timedelta(days=i * 3) for i in range(20)]          # 0~57일 전
    prior = [TODAY - pd.Timedelta(days=100 + i * 6) for i in range(10)]   # 100~154일 전
    dates_by_name = {
        "급증집": surge + prior,
        "죽은스타": [TODAY - pd.Timedelta(days=200 + i * 5) for i in range(20)],
    }
    monkeypatch.setattr(naver, "blog_post_dates", lambda name, token: dates_by_name.get(name, []))
    df = make_roster([{schema.NAME: "급증집"}, {schema.NAME: "죽은스타"}])
    ctx = _ctx(df)

    result = StarLevel().compute(ctx).set_index(signal_base.EST_ID)
    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}

    badge = result.loc[ids["급증집"], signal_base.BADGE]
    assert "월 5.0건" in badge          # 30건/180일 = 월 5건
    assert "+100%" in badge             # (20-10)/10
    assert pd.isna(result.loc[ids["죽은스타"], signal_base.BADGE])

    scored = KnownStar().score({"star_level": result.reset_index()}, ctx)
    assert ids["죽은스타"] not in set(scored[scorer_base.EST_ID])
    assert list(scored[scorer_base.EST_ID]) == [ids["급증집"]]

"""Phase 4 평판 축 — 주소 토큰·M8 버즈·리뷰 모멘텀·목적지 지수 (Naver는 monkeypatch)"""

import pandas as pd
import pytest

from core import schema
from core.area import Area
from datasources import naver
from scorers import base as scorer_base
from scorers.destination_index import DestinationIndex
from signals import base as signal_base
from signals.base import AreaContext
from signals.buzz_momentum import BuzzMomentum
from signals.review_momentum import ReviewMomentum
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
        # 저밀집 골목 (도보 반경 안, 중심에서 ≈250m 동쪽)
        {schema.NAME: "골목의보석", schema.CAT_S: "한식", schema.LAT: 37.4979, schema.LON: 127.0304,
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
                     schema.LON: 127.0304, schema.LICENSED_AT: "2024-01-01"})
    df = make_roster(rows)
    ctx = _ctx(df)

    review = ReviewMomentum().compute(ctx)
    scored = DestinationIndex().score({"review_momentum": review}, ctx)
    scorer_base.validate_score_result(scored)

    ids = {row[schema.NAME]: row[schema.SRC_ID] for _, row in df.iterrows()}
    assert ids["무명집"] not in set(scored[scorer_base.EST_ID])  # 블로그 미관측 — 제외
    ranks = scored.set_index(scorer_base.EST_ID)[scorer_base.RANK]
    assert ranks[ids["골목의보석"]] < ranks[ids["번화가평범"]]  # 저밀집의 같은 관측량이 위


def test_destination_index_empty_without_review_signal():
    df = make_roster([{schema.NAME: "아무집"}])
    scored = DestinationIndex().score({}, _ctx(df))
    assert len(scored) == 0

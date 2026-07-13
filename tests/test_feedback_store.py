"""피드백 저장 계층 — 방문가치/속성 채널 분리, 노출 로그 중복방지, JSON 직렬화 안전성"""

import json

import numpy as np
import pandas as pd
import pytest

from datasources import feedback_store as fs
from signals import base as signal_base


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "FEEDBACK_EVENTS_PATH", tmp_path / "feedback_events.jsonl")
    monkeypatch.setattr(fs, "ATTRIBUTE_EVENTS_PATH", tmp_path / "attribute_events.jsonl")
    monkeypatch.setattr(fs, "EXPOSURE_DIR", tmp_path / "exposures")
    return tmp_path


# ── 신호값 스냅샷 ─────────────────────────────────────────────────────────────
def test_signal_snapshot_extracts_value_raw_badge():
    df1 = pd.DataFrame(
        [{signal_base.EST_ID: "A", signal_base.VALUE: 0.8, signal_base.RAW: 40,
          signal_base.BADGE: "🆕 개업 40일차", signal_base.DETAIL: "..."}]
    )
    df2 = pd.DataFrame(
        [{signal_base.EST_ID: "A", signal_base.VALUE: 0.3, signal_base.RAW: 1.2,
          signal_base.BADGE: None, signal_base.DETAIL: "..."}]
    )
    snap = fs.signal_snapshot({"recent_opening": df1, "survivor": df2}, "A")
    assert snap["recent_opening"] == {"값": 0.8, "원시값": 40, "배지": "🆕 개업 40일차"}
    assert snap["survivor"]["배지"] is None


def test_signal_snapshot_skips_signals_without_this_shop():
    df = pd.DataFrame(
        [{signal_base.EST_ID: "OTHER", signal_base.VALUE: 0.5, signal_base.RAW: 1,
          signal_base.BADGE: None, signal_base.DETAIL: "..."}]
    )
    snap = fs.signal_snapshot({"survivor": df}, "A")
    assert snap == {}


# ── 노출 로그 ────────────────────────────────────────────────────────────────
def test_log_exposure_overwrites_same_day_area_scorer(store):
    now = pd.Timestamp("2026-07-12 10:00:00")
    ranked_v1 = [{"순위": 1, "업소ID": "A", "상호": "가게A", "점수": 0.9, "신호값": {}, "배지": []}]
    fs.log_exposure("weighted_sum", 127.0276, 37.4979, 300, ranked_v1, now=now)
    files = list(fs.EXPOSURE_DIR.glob("*.json"))
    assert len(files) == 1

    ranked_v2 = ranked_v1 + [{"순위": 2, "업소ID": "B", "상호": "가게B", "점수": 0.5, "신호값": {}, "배지": []}]
    fs.log_exposure("weighted_sum", 127.0276, 37.4979, 300, ranked_v2, now=now)
    files = list(fs.EXPOSURE_DIR.glob("*.json"))
    assert len(files) == 1  # 같은 키는 덮어쓴다 — 중복 누적 방지
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(payload["업소목록"]) == 2  # 최신 내용으로 갱신됨


def test_log_exposure_different_scorer_creates_separate_file(store):
    now = pd.Timestamp("2026-07-12 10:00:00")
    ranked = [{"순위": 1, "업소ID": "A", "상호": "가게A", "점수": 0.9, "신호값": {}, "배지": []}]
    fs.log_exposure("weighted_sum", 127.0276, 37.4979, 300, ranked, now=now)
    fs.log_exposure("destination_index", 127.0276, 37.4979, 300, ranked, now=now)
    assert len(list(fs.EXPOSURE_DIR.glob("*.json"))) == 2


# ── 방문가치 피드백 ───────────────────────────────────────────────────────────
def test_record_feedback_last_wins(store):
    fs.record_feedback(
        "A", "가게A", fs.LABEL_UP, "weighted_sum", 127.0276, 37.4979, 300,
        0.9, ["🆕 개업 40일차"], {"recent_opening": {"값": 0.8, "원시값": 40, "배지": "..."}},
        now=pd.Timestamp("2026-07-12 10:00:00"),
    )
    fs.record_feedback(
        "A", "가게A", fs.LABEL_DOWN, "weighted_sum", 127.0276, 37.4979, 300,
        0.9, ["🆕 개업 40일차"], {}, now=pd.Timestamp("2026-07-12 11:00:00"),
    )
    latest = fs.latest_feedback()
    assert latest["A"]["라벨"] == fs.LABEL_DOWN  # 재평가 시 마지막 것이 이긴다


def test_record_feedback_invalid_label_raises(store):
    with pytest.raises(ValueError):
        fs.record_feedback("A", "가게A", "maybe", "weighted_sum", 0, 0, 300, 0.5, [], {})


def test_record_feedback_persists_signal_snapshot_for_lift_analysis(store):
    fs.record_feedback(
        "A", "가게A", fs.LABEL_DOWN, "weighted_sum", 127.0276, 37.4979, 300, 0.9,
        ["🌳 생존자"], {"survivor": {"값": 0.9, "원시값": 5.2, "배지": "🌳 생존자"}},
        now=pd.Timestamp("2026-07-12"),
    )
    events = fs._read_jsonl(fs.FEEDBACK_EVENTS_PATH)
    assert events[0]["신호값"]["survivor"]["원시값"] == 5.2
    assert events[0]["배지"] == ["🌳 생존자"]


# ── 업소 속성 (방문가치와 분리된 채널) ─────────────────────────────────────────
def test_record_attribute_last_wins_per_attribute(store):
    fs.record_attribute("A", "가게A", fs.ATTR_NO_LIQUOR, True, now=pd.Timestamp("2026-07-12 09:00:00"))
    fs.record_attribute("A", "가게A", fs.ATTR_CLOSED, True, now=pd.Timestamp("2026-07-12 09:05:00"))
    attrs = fs.latest_attributes()
    assert attrs["A"] == {fs.ATTR_NO_LIQUOR: True, fs.ATTR_CLOSED: True}

    fs.record_attribute("A", "가게A", fs.ATTR_NO_LIQUOR, False, now=pd.Timestamp("2026-07-12 10:00:00"))
    attrs = fs.latest_attributes()
    assert attrs["A"][fs.ATTR_NO_LIQUOR] is False  # 취소 가능
    assert attrs["A"][fs.ATTR_CLOSED] is True       # 다른 속성은 영향 없음


def test_record_attribute_invalid_raises(store):
    with pytest.raises(ValueError):
        fs.record_attribute("A", "가게A", "모름", True)


# ── JSON 직렬화 안전성 (numpy/NaN이 실데이터에서 넘어온다) ──────────────────────
def test_jsonable_survives_numpy_and_nan(store):
    signal_values = {
        "survivor": {"값": np.float64(0.42), "원시값": np.int64(3), "배지": None},
        "growth_momentum": {"값": float("nan"), "원시값": None, "배지": None},
    }
    fs.record_feedback(
        "A", "가게A", fs.LABEL_UP, "weighted_sum", 127.0276, 37.4979, 300, 0.9, [], signal_values
    )
    events = fs._read_jsonl(fs.FEEDBACK_EVENTS_PATH)
    rec = events[0]["신호값"]
    assert rec["survivor"]["값"] == 0.42 and isinstance(rec["survivor"]["값"], float)
    assert rec["survivor"]["원시값"] == 3 and isinstance(rec["survivor"]["원시값"], int)
    assert rec["growth_momentum"]["값"] is None  # NaN -> null

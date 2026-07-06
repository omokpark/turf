"""플러그인 레지스트리·계약 테스트 — '파일 1개 추가 = 모델 1개 추가' 구조의 감시자"""

import pandas as pd
import pytest

from core.area import Area
from scorers import base as scorer_base
from signals import base as signal_base
from signals import registry
from signals.base import AreaContext, IndicatorResult


@pytest.fixture(autouse=True)
def clean_registries():
    registry.clear()
    scorer_base.clear()
    yield
    registry.clear()
    scorer_base.clear()


def _make_ctx(gangnam_roster):
    return AreaContext(
        area=Area(cx=127.0276, cy=37.4979, radius=300),
        establishments=gangnam_roster,
        rosters={"moi": gangnam_roster},
        today=pd.Timestamp("2026-07-06"),
    )


class FakeSignal:
    id = "fake"
    label = "가짜신호"
    badge_icon = "🧪"
    requires = frozenset({"moi"})

    def compute(self, ctx):
        return pd.DataFrame(
            {
                signal_base.EST_ID: ["TEST-0001"],
                signal_base.VALUE: [0.5],
                signal_base.RAW: [4.2],
                signal_base.BADGE: ["업력 4.2년"],
                signal_base.DETAIL: ["인허가일자 기준"],
            }
        )


class NeedsSeoulData:
    id = "seoul_only"
    label = "서울전용"
    badge_icon = "🌃"
    requires = frozenset({"seoul_pop"})

    def compute(self, ctx):
        raise AssertionError("가용하지 않으면 호출되면 안 된다")


def test_signal_registration_and_availability():
    registry.register_signal(FakeSignal)
    registry.register_signal(NeedsSeoulData)
    available = registry.available_signals({"moi"})
    assert [s.id for s in available] == ["fake"]  # seoul_pop 없으므로 자동 비활성


def test_duplicate_signal_id_rejected():
    registry.register_signal(FakeSignal)
    with pytest.raises(ValueError, match="중복"):
        registry.register_signal(FakeSignal)


def test_signal_output_contract(gangnam_roster):
    registry.register_signal(FakeSignal)
    result = registry.get_signal("fake").compute(_make_ctx(gangnam_roster))
    signal_base.validate_signal_result(result)  # 스키마·값 범위 통과


def test_signal_value_out_of_range_rejected():
    bad = pd.DataFrame(
        {
            signal_base.EST_ID: ["x"],
            signal_base.VALUE: [1.5],  # 0~1 위반
            signal_base.RAW: [1],
            signal_base.BADGE: ["b"],
            signal_base.DETAIL: ["d"],
        }
    )
    with pytest.raises(ValueError, match="0~1"):
        signal_base.validate_signal_result(bad)


def test_indicator_registration():
    class FakeIndicator:
        id = "fake_ind"
        label = "가짜지표"
        requires = frozenset({"moi"})

        def compute(self, ctx):
            return IndicatorResult(current=1.0, previous=0.5, series=None, percentile=80.0, fact="개업이 늘었다")

    registry.register_indicator(FakeIndicator)
    assert [i.id for i in registry.available_indicators({"moi"})] == ["fake_ind"]
    result = registry.get_indicator("fake_ind").compute(None)
    assert isinstance(result, IndicatorResult)


def test_scorer_badge_required():
    """판단 원칙의 계약 테스트: 배지 없는 점수는 거부된다."""
    no_badge = pd.DataFrame(
        {
            scorer_base.EST_ID: ["a", "b"],
            scorer_base.SCORE: [0.9, 0.1],
            scorer_base.RANK: [1, 2],
            scorer_base.BADGES: [["자리회전 3회"], []],  # b에 배지 없음
        }
    )
    with pytest.raises(ValueError, match="배지"):
        scorer_base.validate_score_result(no_badge)

    with_badges = no_badge.assign(**{scorer_base.BADGES: [["자리회전 3회"], ["업력 4.2년"]]})
    scorer_base.validate_score_result(with_badges)

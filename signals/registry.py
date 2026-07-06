"""Signal·AreaIndicator 레지스트리

사용법 (새 모델 파일에서):
    from signals.registry import register_signal

    @register_signal
    class BusinessAge:
        id = "business_age"
        ...

available_*(providers)는 requires가 충족되는 것만 돌려준다 — 데이터 소스가
없는 신호는 UI·스코어러에서 조용히 빠진다.
"""

from signals.base import AreaIndicator, Signal

_SIGNALS: dict[str, Signal] = {}
_INDICATORS: dict[str, AreaIndicator] = {}


def register_signal(cls):
    """Signal 구현 클래스를 등록한다 (클래스 데코레이터, 인스턴스로 보관)."""
    instance = cls() if isinstance(cls, type) else cls
    if instance.id in _SIGNALS:
        raise ValueError(f"Signal id 중복: {instance.id}")
    _SIGNALS[instance.id] = instance
    return cls


def register_indicator(cls):
    instance = cls() if isinstance(cls, type) else cls
    if instance.id in _INDICATORS:
        raise ValueError(f"AreaIndicator id 중복: {instance.id}")
    _INDICATORS[instance.id] = instance
    return cls


def available_signals(providers: set[str]) -> list[Signal]:
    return [s for s in _SIGNALS.values() if s.requires <= providers]


def available_indicators(providers: set[str]) -> list[AreaIndicator]:
    return [i for i in _INDICATORS.values() if i.requires <= providers]


def get_signal(signal_id: str) -> Signal:
    return _SIGNALS[signal_id]


def get_indicator(indicator_id: str) -> AreaIndicator:
    return _INDICATORS[indicator_id]


def clear() -> None:
    """테스트 전용 — 레지스트리 초기화."""
    _SIGNALS.clear()
    _INDICATORS.clear()

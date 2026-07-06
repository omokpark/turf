"""데이터 수급 계층의 공통 계약

Provider: 수동 파일이든 실시간 API든, 호출부가 구분할 수 없는 동일 인터페이스.
- fetch(area)  → ROSTER_COLUMNS 스키마 DataFrame (kind="roster"인 경우)
- freshness(area) → 보유 데이터의 기준 시점. UI가 '데이터 기준일'로 표기해
  낡은 데이터를 사용자가 인지하게 한다.
"""

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

import pandas as pd

from core.area import Area


@runtime_checkable
class Provider(Protocol):
    id: str              # "moi", "semas", "naver"
    kind: str            # "roster"(명부) | "reputation"(평판) | "context"(입지)
    cache_ttl: timedelta

    def fetch(self, area: Area) -> pd.DataFrame: ...

    def freshness(self, area: Area) -> datetime | None: ...


_PROVIDERS: dict[str, Provider] = {}


def register_provider(cls):
    instance = cls() if isinstance(cls, type) else cls
    if instance.id in _PROVIDERS:
        raise ValueError(f"Provider id 중복: {instance.id}")
    _PROVIDERS[instance.id] = instance
    return cls


def get_provider(provider_id: str) -> Provider:
    return _PROVIDERS[provider_id]


def available_providers() -> set[str]:
    return set(_PROVIDERS)


def clear() -> None:
    """테스트 전용."""
    _PROVIDERS.clear()

"""Google Places API 월 호출량 원장(ledger) — 무료 한도 하드 스톱

2025-03 요금 개편(월 $200 크레딧 폐지) 후 SKU별 월 무료 호출량 체계 (2026-07-07 확인,
developers.google.com/maps/billing-and-pricing/pricing):
- Text Search Essentials (IDs Only 필드 마스크): 무제한 무료
- Place Details Pro (businessStatus 등): 월 5,000건 무료, 초과 $17/1천건
- Place Details Enterprise (rating·userRatingCount·regularOpeningHours 등): 월 1,000건
  무료, 초과 $20/1천건

원칙: **무료 한도를 넘는 호출은 코드가 거부한다** (사용자 요구, 2026-07-07). 한도는
무료치의 90%로 잡아 안전 마진을 둔다 — 구글 쪽 집계와 이 원장의 오차(재시도, 타
도구 사용분)를 흡수하기 위함. 원장은 data/cache/places/quota_ledger.json에 월 단위로
기록되어 프로세스 재시작을 넘어 유지된다.

주의: 이 원장은 이 앱의 호출만 센다. 같은 키를 다른 곳에서도 쓴다면 실제 사용량은
더 많을 수 있다 — 그 경우 Google Cloud 콘솔의 할당량(Quotas) 화면에서 키 자체에도
일일 상한을 걸어두는 것을 권장한다 (이중 방어).
"""

import json
from datetime import datetime

from core import config

# SKU id → 월 무료 한도 (None = 무제한). 캡은 무료치 × SAFETY_RATIO.
FREE_TIER = {
    "text_search_ids_only": None,       # Essentials(IDs Only) — 무제한 무료
    "place_details_pro": 5_000,         # businessStatus 등
    "place_details_enterprise": 1_000,  # rating·userRatingCount·영업시간
}
SAFETY_RATIO = 0.9

LEDGER_PATH = config.CACHE_DIR / "places" / "quota_ledger.json"


class QuotaExceeded(RuntimeError):
    """이번 달 무료 한도(안전 마진 반영)에 도달 — 호출을 거부했다."""


def _month_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m")


def _load() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return {}


def _save(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def cap_of(sku: str) -> int | None:
    free = FREE_TIER[sku]
    return None if free is None else int(free * SAFETY_RATIO)


def used(sku: str, now: datetime | None = None) -> int:
    return _load().get(_month_key(now), {}).get(sku, 0)


def remaining(sku: str, now: datetime | None = None) -> int | None:
    cap = cap_of(sku)
    return None if cap is None else max(0, cap - used(sku, now))


def reserve(sku: str, n: int = 1, now: datetime | None = None) -> None:
    """호출 직전에 부른다. 한도를 넘기면 QuotaExceeded — 호출 자체를 막는다.

    성공 시 사용량을 먼저 기록한다(호출 실패 시 약간 과다 계산될 수 있으나,
    과금 방지 목적에는 과다 계산이 과소 계산보다 안전하다).
    """
    if sku not in FREE_TIER:
        raise ValueError(f"알 수 없는 SKU: {sku}")
    cap = cap_of(sku)
    ledger = _load()
    month = _month_key(now)
    current = ledger.get(month, {}).get(sku, 0)
    if cap is not None and current + n > cap:
        raise QuotaExceeded(
            f"Places {sku} 월 한도 도달: {current}/{cap} (무료 {FREE_TIER[sku]}건의 "
            f"{SAFETY_RATIO:.0%} 안전 마진). 다음 달까지 이 SKU 호출을 중단합니다."
        )
    ledger.setdefault(month, {})[sku] = current + n
    _save(ledger)


def summary(now: datetime | None = None) -> dict:
    """UI 표시용: SKU별 {사용량, 한도}."""
    return {
        sku: {"사용": used(sku, now), "한도": cap_of(sku)}
        for sku in FREE_TIER
    }

"""담당구역 즐겨찾기 저장소 — 자주 쓰는 위치를 이름 붙여 저장하고 한 번에 복귀한다.

우편번호 자체는 지오코딩하지 않는다(2026-07-12 검토: VWorld 주소 API가 우편번호
입력을 못 받고, 새 도로명 우편번호는 건물~짧은 도로 구간 단위라 영업사원의
"담당구역"보다 훨씬 작다 — 별도 API 승인까지 받을 실익이 적다). 대신 이름은
자유 텍스트로 두어, 회사가 우편번호·행정동 등 어떤 단위로 구역을 통보하든 그
이름표만 붙이고, 실제 위치는 기존 주소/동 이름 검색으로 정확히 잡아 저장한다.

data/cache/favorites.json — {이름: {cx, cy, 저장시각}}. 이름이 키라서 같은 이름으로
다시 저장하면 위치가 갱신된다(재저장 = 업데이트).
"""

import json
from datetime import datetime

from core import config

FAVORITES_PATH = config.CACHE_DIR / "favorites.json"


def _load() -> dict:
    if FAVORITES_PATH.exists():
        return json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    return {}


def _save(favorites: dict) -> None:
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_PATH.write_text(json.dumps(favorites, ensure_ascii=False, indent=1), encoding="utf-8")


def list_favorites() -> list[dict]:
    """저장 순서대로 [{이름, cx, cy, 저장시각}, ...]."""
    return [{"이름": name, **v} for name, v in _load().items()]


def add_favorite(name: str, cx: float, cy: float, now: datetime | None = None) -> None:
    """이름으로 현재 위치를 저장한다. 같은 이름이 이미 있으면 위치를 갱신한다."""
    name = name.strip()
    if not name:
        raise ValueError("즐겨찾기 이름이 비어 있습니다.")
    favorites = _load()
    favorites[name] = {"cx": cx, "cy": cy, "저장시각": (now or datetime.now()).isoformat()}
    _save(favorites)


def remove_favorite(name: str) -> None:
    favorites = _load()
    favorites.pop(name, None)
    _save(favorites)

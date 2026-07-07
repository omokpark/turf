"""Google Places API (New) 어댑터 — M1 완전판·M7 v2·M2 폐업 교차검증의 데이터원

유일한 유료 API. 모든 HTTP 호출은 **places_quota 원장을 먼저 통과**해야 하며(무료
한도 90%에서 QuotaExceeded로 하드 스톱), 응답은 30일 파일 캐시에 저장된다 — 캐시
히트는 쿼터를 소비하지 않는다.

비용 설계 (2026-07-07 요금 실측 근거 — "헛걸음 제거는 넓게, 정밀 평판은 좁게"):
- find_place_id: Text Search **IDs Only** 필드 마스크 → Essentials SKU, 무제한 무료.
  이름+주소토큰+좌표 바이어스로 place_id만 얻는다.
- business_status: businessStatus만 → **Pro SKU(월 무료 5,000건)**. M2 폐업
  교차검증을 방문 리스트 전체에 넓게 돌릴 수 있다.
- place_snapshot: rating·userRatingCount·regularOpeningHours·businessStatus를 한
  필드 마스크로 묶어 요청 → 과금은 최고 등급 1건(**Enterprise, 월 무료 1,000건**).
  평점·영업시간이 진짜 필요한 최상위 후보에만 쓴다. (평점·리뷰수도 영업시간과 같은
  Enterprise 필드라 영업시간을 빼도 등급이 내려가지 않는다 — 분리 실익 없음.)

⚠️ 실호출 검증 전 (키 미수령) — 엔드포인트·필드 마스크는 공식 문서 기준이며 키 수령
후 스모크 필요.
"""

import hashlib
import json
import urllib.request
from datetime import datetime, timedelta

from core import config
from datasources import places_quota

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
CACHE_TTL = timedelta(days=30)  # 계획서 Phase 6: 격자 캐시 30일

# Details 1회로 M1(평점·리뷰수)+M7v2(영업시간)+M2(영업상태)를 전부 커버하는 마스크.
# rating·userRatingCount·regularOpeningHours가 Enterprise 필드라 과금은 Enterprise 1건.
SNAPSHOT_FIELD_MASK = "id,businessStatus,rating,userRatingCount,regularOpeningHours"


def available() -> bool:
    try:
        config.places_key()
        return True
    except RuntimeError:
        return False


def _cached_json(cache_name: str, fetch) -> dict | None:
    path = config.CACHE_DIR / "places" / cache_name
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _post(url: str, body: dict, field_mask: str) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config.places_key(),
            "X-Goog-FieldMask": field_mask,
        },
    )
    return json.load(urllib.request.urlopen(req, timeout=15))


def _get(url: str, field_mask: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"X-Goog-Api-Key": config.places_key(), "X-Goog-FieldMask": field_mask},
    )
    return json.load(urllib.request.urlopen(req, timeout=15))


def find_place_id(name: str, addr_token: str, lat: float, lon: float) -> str | None:
    """1차 패스: 이름+주소토큰으로 place_id만 찾는다 (IDs Only — 무제한 무료 SKU)."""
    query = f"{name} {addr_token}".strip()
    digest = hashlib.sha1(f"{query}_{lat:.4f}_{lon:.4f}".encode()).hexdigest()[:16]

    def fetch():
        places_quota.reserve("text_search_ids_only")
        body = {
            "textQuery": query,
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 500.0}},
            "pageSize": 1,
        }
        return _post(SEARCH_URL, body, "places.id")

    data = _cached_json(f"id_{digest}.json", fetch)
    places = (data or {}).get("places", [])
    return places[0]["id"] if places else None


def business_status(place_id: str) -> str | None:
    """M2 폐업 교차검증 전용 — businessStatus만 (Pro, 월 4,500건 캡).

    평판 스냅샷과 등급을 분리해 "헛걸음 제거는 넓게(Pro), 정밀 평판은 좁게(Enterprise)"
    를 가능하게 한다 (사용자 결정 2026-07-07). 반환: "OPERATIONAL" |
    "CLOSED_TEMPORARILY" | "CLOSED_PERMANENTLY" | None(조회 실패).
    """

    def fetch():
        places_quota.reserve("place_details_pro")
        return _get(DETAILS_URL.format(place_id=place_id), "id,businessStatus")

    data = _cached_json(f"status_{place_id}.json", fetch)
    return (data or {}).get("businessStatus")


def place_snapshot(place_id: str) -> dict | None:
    """정밀 평판 스냅샷 — 평점·리뷰수·영업시간·영업상태를 Details 1회로
    (Enterprise, 월 900건 캡 — 무료 신호로 추린 최상위 후보에만 쓸 것).

    반환 예: {"businessStatus": "OPERATIONAL", "rating": 4.4, "userRatingCount": 213,
             "regularOpeningHours": {...}} — 원본 필드 그대로.
    """

    def fetch():
        places_quota.reserve("place_details_enterprise")
        return _get(DETAILS_URL.format(place_id=place_id), SNAPSHOT_FIELD_MASK)

    return _cached_json(f"snap_{place_id}.json", fetch)


# ── 응답 해석 헬퍼 (관측 사실 → 배지 문구) ───────────────────────────────────

LATE_NIGHT_HOUR = 23  # 이 시각 이후까지 열면 심야 영업으로 본다


def is_late_night(regular_opening_hours: dict | None) -> bool:
    """자정 넘겨 닫거나(요일 롤오버) 23시 이후까지 여는 날이 하루라도 있는가."""
    for period in (regular_opening_hours or {}).get("periods", []):
        open_, close = period.get("open"), period.get("close")
        if not close:  # close 없음 = 24시간 영업
            return True
        if open_ and close.get("day") != open_.get("day"):  # 자정 롤오버
            return True
        if close.get("hour", 0) >= LATE_NIGHT_HOUR:
            return True
    return False


def status_badge(status: str | None) -> str | None:
    """M2 폐업 교차검증 배지 — 인허가상 영업중인데 구글 기준 닫힌 집 = 헛걸음 후보."""
    if status == "CLOSED_PERMANENTLY":
        return "⚠️ 구글 기준 폐업 — 헛걸음 주의 (인허가 폐업신고 지연 가능)"
    if status == "CLOSED_TEMPORARILY":
        return "⚠️ 구글 기준 임시 휴업"
    return None


def snapshot_badges(snap: dict | None) -> list[str]:
    """평판 스냅샷 → 관측 사실 배지 (M1 완전판 축·M7 v2 축)."""
    if not snap:
        return []
    badges = []
    rating, count = snap.get("rating"), snap.get("userRatingCount")
    if rating is not None and count:
        badges.append(f"⭐ 구글 평점 {rating} (리뷰 {count:,}개)")
    if is_late_night(snap.get("regularOpeningHours")):
        badges.append(f"🌃 심야 영업 ({LATE_NIGHT_HOUR}시 이후까지)")
    closed = status_badge(snap.get("businessStatus"))
    if closed:
        badges.append(closed)
    return badges

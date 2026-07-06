"""Naver 블로그 검색 — 리뷰 모멘텀의 무료 프록시 (M1 Naver판 · M8 버즈 모멘텀)

- 쿼리는 항상 "상호 + 주소 토큰"으로 만든다: 동명 업소 블로그 오매칭 방어
  (REDESIGN_PLAN 함정 목록 — '홍수'처럼 흔한 이름은 토큰 없이는 전국 글이 섞인다).
- 결과는 postdate로 기간 필터해서 센다. display 최대 100건이라 기간 내 글이 그보다
  많으면 과소집계되는데(=100에서 캡), 신호는 log를 씌워 쓰므로 왜곡이 작다.
- 파일 캐시 TTL 7일 (data/cache/naver/) — 일 25,000 쿼터 방어의 1차 수단.
  2차 수단은 호출 범위 자체의 통제: M8은 골든타임 리스트만, M1은 반경 내 영업 업소만.
"""

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from core import config

BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"
CACHE_TTL = timedelta(days=7)
_RATE_SLEEP_S = 0.06  # 개발계정 초당 한도(≈10 QPS) 방어
_MAX_RETRIES = 3

_DONG_RE = re.compile(r"(\S+동)(?=\s|$)")
_ROAD_RE = re.compile(r"(\S+(?:로|길))(?=\s|\d|$)")
_GU_RE = re.compile(r"(\S+구)(?=\s|$)")


def available() -> bool:
    try:
        config.naver_keys()
        return True
    except RuntimeError:
        return False


def address_token(road_addr: str | None, jibun_addr: str | None) -> str:
    """오매칭 방어용 지역 토큰: 지번의 동 > 도로명의 로/길 > 구 순으로 고른다."""
    for pattern, addr in ((_DONG_RE, jibun_addr), (_ROAD_RE, road_addr), (_GU_RE, road_addr or jibun_addr)):
        if addr:
            m = pattern.search(str(addr))
            if m:
                return m.group(1)
    return ""


def _cache_path(query: str):
    digest = hashlib.sha1(query.encode()).hexdigest()[:16]
    return config.CACHE_DIR / "naver" / f"blog_{digest}.json"


def _search_blog_raw(query: str, display: int = 100) -> dict:
    """블로그 검색 1회 호출 (최신순). 파일 캐시 7일."""
    path = _cache_path(query)
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))

    cid, secret = config.naver_keys()
    url = f"{BLOG_URL}?query={urllib.parse.quote(query)}&display={display}&sort=date"
    req = urllib.request.Request(url, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret})
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            time.sleep(_RATE_SLEEP_S)
            data = json.load(urllib.request.urlopen(req, timeout=10))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception as e:  # 429 포함 — 지수 대기 후 재시도
            last_error = e
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Naver 블로그 검색 실패 ({_MAX_RETRIES}회 재시도): {last_error}")


def blog_posts_since(name: str, token: str, since: pd.Timestamp) -> tuple[int, pd.Timestamp | None]:
    """(since 이후 포스팅 수, 가장 최근 포스팅 날짜). 토큰이 비면 (0, None) — 오매칭 방지 우선."""
    if not token:
        return 0, None
    data = _search_blog_raw(f"{name} {token}")
    count = 0
    latest = None
    for item in data.get("items", []):
        postdate = pd.to_datetime(item.get("postdate", ""), format="%Y%m%d", errors="coerce")
        if pd.isna(postdate):
            continue
        if latest is None or postdate > latest:
            latest = postdate
        if postdate >= since:
            count += 1
    return count, latest

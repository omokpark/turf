"""서울 열린데이터광장 — 행정동 생활인구 (M7 야간 상권 지수의 심야 인구 축)

- 생활인구(SPOP_LOCAL_RESD_DONG): 기준일×시간대(00~23)×행정동코드(8자리)별 총생활인구.
  데이터가 1~2주 지연 게시되므로 최근 날짜부터 며칠 거슬러가며 있는 날을 찾는다.
- 좌표→행정동 매핑은 VWorld 리버스 지오코딩(getAddress)의 level4AC(행정기관코드
  10자리) 앞 8자리 — 강남역→역삼1동(11680640)으로 실검증(2026-07-07).
- 서울 밖 좌표는 행정동 조회가 실패하므로 available()과 별개로 결과가 None일 수 있다
  (신호는 requires로 켜지되 구역이 서울 밖이면 우아하게 빈 결과).

파일 캐시 7일 — 생활인구는 일 단위 갱신이지만 신호 용도로는 주 단위면 충분하다.
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from core import config

SPOP_URL = "http://openapi.seoul.go.kr:8088/{key}/json/SPOP_LOCAL_RESD_DONG/1/30/{date}/%20/{dong}"
VWORLD_ADDR_URL = "https://api.vworld.kr/req/address"
CACHE_TTL = timedelta(days=7)
NIGHT_HOURS = ("23", "00", "01", "02", "03", "04")  # 심야 정의: 23시~04시
DATA_LAG_DAYS = 14  # 생활인구 게시 지연 — 이 날짜부터 거슬러 탐색
LOOKBACK_TRIES = 7


def available() -> bool:
    try:
        config.seoul_key()
        return True
    except RuntimeError:
        return False


def _cached_json(cache_name: str, fetch) -> dict | None:
    path = config.CACHE_DIR / "seoul" / cache_name
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def dong_of(cx: float, cy: float) -> tuple[str, str] | None:
    """좌표 → (행정동코드 8자리, 행정동명). 매핑 실패(서울 밖 포함) 시 None."""

    def fetch():
        url = (
            f"{VWORLD_ADDR_URL}?service=address&request=getAddress&version=2.0"
            f"&crs=epsg:4326&point={cx},{cy}&type=both&format=json&key={config.vworld_key()}"
        )
        body = json.load(urllib.request.urlopen(url, timeout=15))
        response = body.get("response", {})
        if response.get("status") != "OK":
            return None
        for r in response.get("result", []):
            s = r.get("structure", {})
            code = (s.get("level4AC") or "").strip()
            if code:
                return {"code": code[:8], "name": s.get("level4A", "")}
        return None

    data = _cached_json(f"dong_{cx:.5f}_{cy:.5f}.json", fetch)
    if not data:
        return None
    return data["code"], data["name"]


def night_population_share(dong_code: str) -> dict | None:
    """행정동의 심야(23~04시) 평균 생활인구 / 전일 평균 비율.

    반환: {"비율": float, "심야평균": float, "전일평균": float, "기준일": "YYYYMMDD"} 또는 None.
    """

    def fetch():
        key = config.seoul_key()
        for back in range(LOOKBACK_TRIES):
            date = (datetime.now() - timedelta(days=DATA_LAG_DAYS + back)).strftime("%Y%m%d")
            url = SPOP_URL.format(key=urllib.parse.quote(key), date=date, dong=dong_code)
            body = json.load(urllib.request.urlopen(url, timeout=15))
            rows = body.get("SPOP_LOCAL_RESD_DONG", {}).get("row") or []
            hours = {r["TMZON_PD_SE"].zfill(2): float(r["TOT_LVPOP_CO"]) for r in rows}
            if len(hours) >= 20:  # 하루치가 온전히 있는 날만 사용
                night = sum(hours[h] for h in NIGHT_HOURS if h in hours) / len(NIGHT_HOURS)
                allday = sum(hours.values()) / len(hours)
                return {
                    "비율": round(night / allday, 4) if allday > 0 else None,
                    "심야평균": round(night, 1),
                    "전일평균": round(allday, 1),
                    "기준일": date,
                }
        return None

    return _cached_json(f"spop_{dong_code}.json", fetch)

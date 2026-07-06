"""행정안전부 지방행정 인허가 조회서비스 API 어댑터

구 LOCALDATA(2026-04-16 폐쇄)의 대체. 2026-07-06 실호출로 검증한 스펙:
  엔드포인트: https://apis.data.go.kr/1741000/{서비스}/info
  서비스: general_restaurants(일반음식점) / singing_bars(단란주점) / entertainment_bars(유흥주점)
  페이징: pageNo, numOfRows(최대 100)
  필터: cond[LCPMT_YMD::GTE/LT](인허가일자), cond[SALS_STTS_CD::EQ](영업상태),
        cond[OPN_ATMY_GRP_CD::EQ](개방자치단체코드), cond[DAT_UPDT_PNT::GTE/LT](갱신시점, 증분)
  좌표: CRD_INFO_X/Y — EPSG:5174 (신규 인허가 건은 공백일 수 있음 → 해당 행은 좌표 NaN 유지)

과거 이력 전체가 보존돼 있다(전국 246만 행 중 폐업 173만 포함) — 시계열은 이
데이터의 인허가일자·폐업일자 컬럼에서 파생된다. API를 기간별로 여러 번 부를 필요 없음.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
from pyproj import Transformer

from core import config, schema

BASE_URL = "https://apis.data.go.kr/1741000"
PAGE_SIZE = 100  # API 상한
REQUEST_INTERVAL_S = 0.15  # 과속 방지 — 일 10,000회 한도 내에서도 서버 예의
MAX_RETRIES = 3

# 업종 → 서비스 경로. 새 업종(휴게음식점 등)은 여기 한 줄 추가로 확장.
SERVICES = {
    "일반음식점": "general_restaurants",
    "단란주점": "singing_bars",
    "유흥주점": "entertainment_bars",
}

_TRANSFORMER = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


def fetch_pages(
    category: str,
    conds: dict[str, str] | None = None,
    max_pages: int | None = None,
    on_progress=None,
) -> pd.DataFrame:
    """조건에 맞는 전 페이지를 수집해 원본 필드 그대로의 DataFrame으로 반환한다.

    conds 예: {"OPN_ATMY_GRP_CD::EQ": "3220000"} (강남구)
    on_progress: (page, total_pages, total_count) 콜백 — CLI 진행 표시용.
    """
    service = SERVICES[category]
    key = urllib.parse.quote(config.data_go_kr_key())
    rows: list[dict] = []
    page = 1
    total_count = None
    while True:
        query = f"serviceKey={key}&pageNo={page}&numOfRows={PAGE_SIZE}&returnType=json"
        for cond_key, value in (conds or {}).items():
            query += f"&{urllib.parse.quote(f'cond[{cond_key}]')}={urllib.parse.quote(value)}"
        body = _request(f"{BASE_URL}/{service}/info?{query}")
        response = body.get("response", {})
        header = response.get("header", {})
        if header.get("resultCode") not in ("0", "00"):
            raise RuntimeError(f"행안부 API 오류: {header.get('resultCode')}/{header.get('resultMsg')}")
        payload = response.get("body", {})
        total_count = int(payload.get("totalCount", 0))
        items = payload.get("items") or {}
        page_rows = items.get("item") or []
        if isinstance(page_rows, dict):  # 1건이면 dict로 오는 XML 관례 방어
            page_rows = [page_rows]
        rows.extend(page_rows)

        total_pages = max(1, -(-total_count // PAGE_SIZE))
        if on_progress:
            on_progress(page, total_pages, total_count)
        if page >= total_pages or not page_rows:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL_S)
    return pd.DataFrame(rows)


def normalize(raw: pd.DataFrame, category: str) -> pd.DataFrame:
    """API 원본 필드를 ROSTER 스키마로 정규화한다.

    구 license_fetcher.load_licenses와 같은 정책:
    - 인허가일자 없는 행 제거 (분석 축이 없으므로)
    - 좌표는 있으면 EPSG:5174→WGS84 변환, 한반도 밖이면 NaN 처리
    - 좌표 없는 행은 유지한다 (구현 차이): 신규 인허가 건이 좌표 공백으로 오는 것을
      확인했고, 최근 개업 신호에서 지오코딩 폴백으로 살릴 수 있기 때문.
    """
    if len(raw) == 0:
        return schema.empty_roster()

    out = pd.DataFrame()
    out[schema.SRC] = "moi"
    out[schema.SRC_ID] = raw["MNG_NO"].astype(str)
    out[schema.NAME] = raw["BPLC_NM"].astype(str).str.strip()
    out[schema.CAT_L] = None
    out[schema.CAT_M] = None
    # 업태구분명이 비면 업종 카테고리 자체(일반음식점 등)로 대체
    bzstat = raw["BZSTAT_SE_NM"].astype(str).str.strip()
    out[schema.CAT_S] = bzstat.where(bzstat != "", category)
    out[schema.ADDR_ROAD] = raw["ROAD_NM_ADDR"].astype(str).str.strip()
    out[schema.ADDR_JIBUN] = raw["LOTNO_ADDR"].astype(str).str.strip()

    x = pd.to_numeric(raw["CRD_INFO_X"], errors="coerce")
    y = pd.to_numeric(raw["CRD_INFO_Y"], errors="coerce")
    lon, lat = _TRANSFORMER.transform(x.values, y.values)
    out[schema.LON] = lon
    out[schema.LAT] = lat
    # 한반도 밖 좌표는 이상치 — 행을 버리지 않고 좌표만 무효화
    bad = ~(
        pd.Series(lon).between(*schema.LON_RANGE) & pd.Series(lat).between(*schema.LAT_RANGE)
    )
    out.loc[bad.values, [schema.LON, schema.LAT]] = None

    out[schema.LICENSED_AT] = pd.to_datetime(raw["LCPMT_YMD"], format="mixed", errors="coerce")
    out[schema.CLOSED_AT] = pd.to_datetime(raw["CLSBIZ_YMD"], format="mixed", errors="coerce")
    # SALS_STTS_CD: 01=영업/정상 (구 LOCALDATA 영업상태구분코드 "1"과 동일 의미)
    out[schema.IS_OPEN] = raw["SALS_STTS_CD"].astype(str).str.strip().isin(("01", "1"))
    out[schema.AREA_M2] = pd.to_numeric(raw["LCTN_AREA"], errors="coerce")

    out = out.dropna(subset=[schema.LICENSED_AT]).reset_index(drop=True)
    out[schema.SRC] = out[schema.SRC].astype(str)
    schema.validate_roster(out)
    return out


def fetch_district(district_code: str, category: str, on_progress=None) -> pd.DataFrame:
    """개방자치단체 1곳의 해당 업종 인허가 전체(폐업 포함)를 ROSTER로 반환한다."""
    raw = fetch_pages(category, {"OPN_ATMY_GRP_CD::EQ": district_code}, on_progress=on_progress)
    return normalize(raw, category)


def fetch_updated_since(category: str, since: str, on_progress=None) -> pd.DataFrame:
    """증분 갱신: 갱신시점(YYYYMMDDHHMMSS) 이후 변경분만 ROSTER로 반환한다."""
    raw = fetch_pages(category, {"DAT_UPDT_PNT::GTE": since}, on_progress=on_progress)
    return normalize(raw, category)


def _request(url: str) -> dict:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2**attempt)  # 1, 2, 4초 백오프
    raise RuntimeError(f"행안부 API 호출 실패 ({MAX_RETRIES}회 재시도): {last_error}")

"""
소상공인시장진흥공단 상가(상권)정보 API - 반경내 상권조회
입력: cx(경도), cy(위도), radius(반경, m)
출력: 상가업소 리스트 [{상호, 상권업종대분류명, 상권업종중분류명, 상권업종소분류명, 도로명주소, 위도, 경도}, ...]
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius"
NUM_OF_ROWS = 1000


def fetch_shops(cx: float, cy: float, radius: int) -> list[dict]:
    """반경 내 상가업소 목록을 페이징 처리하여 모두 수집한다."""
    service_key = os.getenv("SGIS_API_KEY")
    if not service_key:
        raise RuntimeError(".env에 SGIS_API_KEY가 설정되어 있지 않습니다.")

    shops = []
    page_no = 1

    while True:
        params = {
            "serviceKey": service_key,
            "type": "json",
            "pageNo": page_no,
            "numOfRows": NUM_OF_ROWS,
            "cx": cx,
            "cy": cy,
            "radius": radius,
        }
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        header = data.get("header", {})
        if header.get("resultCode") != "00":
            raise RuntimeError(f"API 오류: {header.get('resultMsg')}")

        body = data.get("body", {})
        items = body.get("items", [])
        for item in items:
            shops.append(
                {
                    "상호": item.get("bizesNm"),
                    "상권업종대분류명": item.get("indsLclsNm"),
                    "상권업종중분류명": item.get("indsMclsNm"),
                    "상권업종소분류명": item.get("indsSclsNm"),
                    "도로명주소": item.get("rdnmAdr"),
                    "위도": float(item.get("lat")),
                    "경도": float(item.get("lon")),
                }
            )

        total_count = body.get("totalCount", 0)
        if page_no * NUM_OF_ROWS >= total_count or not items:
            break
        page_no += 1

    return shops

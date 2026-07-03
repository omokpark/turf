"""소상공인시장진흥공단 상권업종분류 코드 조회"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/smallUpjongList"
FOOD_LCLS_CD = "I2"


def get_food_categories() -> list[str]:
    """전국 공통 음식 업종 소분류명 목록을 가나다순으로 반환한다."""
    service_key = os.getenv("SGIS_API_KEY")
    if not service_key:
        raise RuntimeError(".env에 SGIS_API_KEY가 설정되어 있지 않습니다.")

    params = {"serviceKey": service_key, "type": "json", "indsLclsCd": FOOD_LCLS_CD}
    response = requests.get(API_URL, params=params, timeout=10)
    response.raise_for_status()
    items = response.json()["body"]["items"]
    return sorted({item["indsSclsNm"] for item in items})

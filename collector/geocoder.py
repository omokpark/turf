"""VWorld 주소검색 API - 주소/지번 → 좌표 변환"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.vworld.kr/req/address"


def geocode_address(address: str) -> tuple[float, float] | None:
    """주소 또는 지번을 (cx, cy) 좌표로 변환한다. 찾지 못하면 None."""
    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 VWORLD_API_KEY가 설정되어 있지 않습니다.")

    for addr_type in ("road", "parcel"):
        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": "epsg:4326",
            "address": address,
            "format": "json",
            "type": addr_type,
            "key": api_key,
        }
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        result = response.json().get("response", {})
        if result.get("status") == "OK":
            point = result["result"]["point"]
            return float(point["x"]), float(point["y"])

    return None

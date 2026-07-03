"""VWorld 주소검색 API - 주소/지번 → 좌표 변환"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.vworld.kr/req/address"
SEARCH_API_URL = "https://api.vworld.kr/req/search"


def geocode_address(address: str) -> dict | None:
    """주소 또는 지번을 후보 정보로 변환한다. 찾지 못하면 None.

    VWorld 주소 API는 퍼지 매칭을 하기 때문에(예: '삼성역' -> 경산시 '삼성역길') 결과가
    있다고 해서 사용자가 의도한 위치라고 확신할 수 없다 — 항상 후보로만 반환하고,
    실제 이동은 호출 쪽에서 사용자 확인을 거친 뒤에 한다.
    반환: {"title": 정제된 주소, "address": 정제된 주소, "cx": ..., "cy": ...}
    """
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
            refined = result.get("refined", {}).get("text", address)
            return {"title": refined, "address": refined, "cx": float(point["x"]), "cy": float(point["y"])}

    return None


def search_places(query: str, size: int = 10) -> list[dict]:
    """장소명(POI)으로 후보 목록을 검색한다. 예: 지하철역, 랜드마크 이름.

    동명 장소가 여러 지역에 있을 수 있어(예: '삼성역') 결과가 여러 건일 수 있다.
    """
    api_key = os.getenv("VWORLD_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 VWORLD_API_KEY가 설정되어 있지 않습니다.")

    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "epsg:4326",
        "query": query,
        "type": "place",
        "size": size,
        "format": "json",
        "errorFormat": "json",
        "key": api_key,
    }
    response = requests.get(SEARCH_API_URL, params=params, timeout=10)
    response.raise_for_status()
    result = response.json().get("response", {})
    if result.get("status") != "OK":
        return []

    candidates = []
    for item in result.get("result", {}).get("items", []):
        point = item.get("point", {})
        address = item.get("address", {})
        candidates.append(
            {
                "title": item.get("title"),
                "address": address.get("road") or address.get("parcel") or "",
                "cx": float(point["x"]),
                "cy": float(point["y"]),
            }
        )
    return candidates

"""환경변수·경로·공용 상수의 단일 출처

모든 모듈은 os.getenv를 직접 부르지 말고 여기서 가져온다.
키가 없을 때의 실패는 각 datasource가 fetch 시점에 일으킨다 (import 시점 아님).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"


def data_go_kr_key() -> str:
    """공공데이터포털(data.go.kr) 공용 인증키.

    역사적으로 .env에 SGIS_API_KEY라는 이름으로 저장돼 왔다(SEMAS 상가정보 API용으로
    처음 발급받았기 때문). 실제로는 행안부 인허가 API 등 data.go.kr 전체에 쓰는 키다.
    """
    key = os.getenv("DATA_GO_KR_API_KEY") or os.getenv("SGIS_API_KEY")
    if not key:
        raise RuntimeError(".env에 DATA_GO_KR_API_KEY(또는 SGIS_API_KEY)가 설정되어 있지 않습니다.")
    return key


def vworld_key() -> str:
    key = os.getenv("VWORLD_API_KEY")
    if not key:
        raise RuntimeError(".env에 VWORLD_API_KEY가 설정되어 있지 않습니다.")
    return key


def naver_keys() -> tuple[str, str]:
    cid, secret = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        raise RuntimeError(".env에 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET이 설정되어 있지 않습니다.")
    return cid, secret

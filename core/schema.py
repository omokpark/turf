"""정규화 스키마 — 모든 계층이 공유하는 컬럼 계약

문제의식: SEMAS는 '상호', 구 LOCALDATA는 '사업장명'처럼 소스마다 같은 것을 다른
이름으로 부른다. 소스별 이름 → 여기 상수로의 변환은 각 datasource 어댑터의 책임이고,
그 이후의 모든 계층(matcher·signals·scorers·UI)은 이 상수만 사용한다.
컬럼명 자체는 한글을 유지한다 — UI 표시명과 일치시켜 변환 계층을 없애기 위함.
"""

import pandas as pd

# ── ROSTER: 모든 명부(roster) 프로바이더가 반환하는 공통 스키마 ──────────────
SRC = "출처"            # str: "moi" | "semas" | "naver" ...
SRC_ID = "출처ID"       # str|None: 소스 내 고유키 (행안부 관리번호, SEMAS bizesId)
NAME = "상호"
CAT_L = "업종대"        # 없으면 None (인허가 데이터는 소분류만 가짐)
CAT_M = "업종중"
CAT_S = "업종소"        # 인허가의 업태구분명, SEMAS의 상권업종소분류명
ADDR_ROAD = "도로명주소"
ADDR_JIBUN = "지번주소"
LAT = "위도"
LON = "경도"
# 인허가 계열 소스만 채우는 컬럼 (다른 소스는 NaN/NaT)
LICENSED_AT = "인허가일자"   # datetime
CLOSED_AT = "폐업일자"       # datetime | NaT
IS_OPEN = "영업중"           # bool
AREA_M2 = "소재지면적"       # float, ㎡

ROSTER_COLUMNS = [
    SRC, SRC_ID, NAME, CAT_L, CAT_M, CAT_S,
    ADDR_ROAD, ADDR_JIBUN, LAT, LON,
    LICENSED_AT, CLOSED_AT, IS_OPEN, AREA_M2,
]

# 좌표 유효 범위 (한반도) — 이상치 제거 기준
LON_RANGE = (124.0, 132.0)
LAT_RANGE = (33.0, 39.0)


def validate_roster(df: pd.DataFrame) -> None:
    """어댑터 출력이 ROSTER 계약을 지키는지 검증한다. 계약 위반은 조용히 넘기지 않는다."""
    missing = set(ROSTER_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"ROSTER 스키마 위반 — 누락 컬럼: {sorted(missing)}")
    if len(df) == 0:
        return
    if not pd.api.types.is_datetime64_any_dtype(df[LICENSED_AT]):
        raise ValueError(f"{LICENSED_AT} 는 datetime이어야 합니다 (현재 {df[LICENSED_AT].dtype})")
    if not pd.api.types.is_datetime64_any_dtype(df[CLOSED_AT]):
        raise ValueError(f"{CLOSED_AT} 는 datetime이어야 합니다 (현재 {df[CLOSED_AT].dtype})")
    if df[IS_OPEN].dtype != bool:
        raise ValueError(f"{IS_OPEN} 은 bool이어야 합니다 (현재 {df[IS_OPEN].dtype})")
    coords = df[[LON, LAT]].dropna()
    bad = coords[
        ~(coords[LON].between(*LON_RANGE) & coords[LAT].between(*LAT_RANGE))
    ]
    if len(bad) > 0:
        raise ValueError(f"한반도 밖 좌표 {len(bad)}행 — 어댑터에서 이상치를 제거해야 합니다.")


def empty_roster() -> pd.DataFrame:
    """스키마를 지키는 빈 명부 — '데이터 없음'과 '스키마 위반'을 구분하기 위해 사용."""
    df = pd.DataFrame(columns=ROSTER_COLUMNS)
    df[LICENSED_AT] = pd.to_datetime(df[LICENSED_AT])
    df[CLOSED_AT] = pd.to_datetime(df[CLOSED_AT])
    df[IS_OPEN] = df[IS_OPEN].astype(bool)
    return df

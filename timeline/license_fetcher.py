"""행정안전부 지방행정 인허가(LOCALDATA) CSV 로드·정규화

데이터 출처: https://www.localdata.go.kr → [데이터받기] → 업종별 전체 CSV
- 일반음식점(07_24_04_P)이 주류 판매 가능 업소의 본체. 필요 시 단란주점·유흥주점 확장.
- 사이트가 프로그램 접근을 막는 경우가 있어(2026-07 확인: curl 접속 불가) 브라우저로
  월 1회 수동 다운로드해 data/ 폴더에 두는 것을 기본 운영으로 한다.

출력 스키마 (normalize 후):
  사업장명, 업태구분명, 인허가일자(datetime), 폐업일자(datetime|NaT),
  영업중(bool), 소재지면적(float, ㎡), 도로명주소, 지번주소, 위도, 경도
"""

from pathlib import Path

import pandas as pd
from pyproj import Transformer

# LOCALDATA 좌표계: 중부원점TM(EPSG:5174) → WGS84(EPSG:4326)
_TRANSFORMER = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)

# LOCALDATA 표준 CSV 컬럼명 → 내부 컬럼명
_COLUMN_MAP = {
    "사업장명": "사업장명",
    "업태구분명": "업태구분명",
    "인허가일자": "인허가일자",
    "폐업일자": "폐업일자",
    "영업상태구분코드": "영업상태구분코드",  # 1=영업/정상, 3=폐업
    "소재지면적": "소재지면적",
    "도로명전체주소": "도로명주소",
    "소재지전체주소": "지번주소",
    "좌표정보(x)": "x",
    "좌표정보(y)": "y",
}
# 일부 배포본은 괄호 없이 'X좌표'/'좌표정보x' 형태를 쓰기도 한다
_X_ALIASES = ["좌표정보(x)", "좌표정보(X)", "좌표정보x", "X좌표"]
_Y_ALIASES = ["좌표정보(y)", "좌표정보(Y)", "좌표정보y", "Y좌표"]


def load_licenses(csv_path: str | Path) -> pd.DataFrame:
    """LOCALDATA 인허가 CSV를 읽어 정규화된 DataFrame을 반환한다."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} 가 없습니다. https://www.localdata.go.kr → 데이터받기에서 "
            "일반음식점 CSV를 내려받아 이 경로에 두세요."
        )

    df = _read_csv_any_encoding(csv_path)
    df = _rename_columns(df)

    required = {"사업장명", "인허가일자", "영업상태구분코드", "x", "y"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"인허가 CSV에 기대한 컬럼이 없습니다: {missing} — LOCALDATA 원본이 맞는지 확인하세요.")

    out = pd.DataFrame()
    out["사업장명"] = df["사업장명"].astype(str).str.strip()
    out["업태구분명"] = df.get("업태구분명", pd.Series(dtype=str)).astype(str).str.strip()
    out["인허가일자"] = pd.to_datetime(df["인허가일자"], format="mixed", errors="coerce")
    out["폐업일자"] = pd.to_datetime(df.get("폐업일자"), format="mixed", errors="coerce")
    # 영업상태구분코드: 1=영업/정상, 2=휴업, 3=폐업, 4=취소/말소 등. "지금 살아있는가"만 판단.
    out["영업중"] = df["영업상태구분코드"].astype(str).str.strip() == "1"
    out["소재지면적"] = pd.to_numeric(df.get("소재지면적"), errors="coerce")
    out["도로명주소"] = df.get("도로명주소", pd.Series(dtype=str)).astype(str).str.strip()
    out["지번주소"] = df.get("지번주소", pd.Series(dtype=str)).astype(str).str.strip()

    x = pd.to_numeric(df["x"], errors="coerce")
    y = pd.to_numeric(df["y"], errors="coerce")
    lon, lat = _TRANSFORMER.transform(x.values, y.values)
    out["경도"] = lon
    out["위도"] = lat

    # 좌표·인허가일자 없는 행은 분석에 쓸 수 없으므로 제거
    out = out.dropna(subset=["인허가일자"])
    out = out[out["경도"].notna() & out["위도"].notna()]
    # 좌표 이상치(한반도 밖) 제거
    out = out[(out["경도"].between(124, 132)) & (out["위도"].between(33, 39))]
    return out.reset_index(drop=True)


def _read_csv_any_encoding(csv_path: Path) -> pd.DataFrame:
    """LOCALDATA CSV는 배포 시기에 따라 cp949 또는 utf-8이다."""
    for encoding in ("cp949", "utf-8", "utf-8-sig"):
        try:
            return pd.read_csv(csv_path, encoding=encoding, dtype=str, low_memory=False)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"{csv_path} 인코딩을 해석하지 못했습니다 (cp949/utf-8 모두 실패).")


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for src, dst in _COLUMN_MAP.items():
        if src in df.columns:
            rename[src] = dst
    for alias in _X_ALIASES:
        if alias in df.columns:
            rename[alias] = "x"
            break
    for alias in _Y_ALIASES:
        if alias in df.columns:
            rename[alias] = "y"
            break
    return df.rename(columns=rename)

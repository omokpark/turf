"""datasources/moi_api.normalize — 실 API 응답 구조(2026-07-06 캡처) 기반 검증"""

import pandas as pd
import pytest

from core import schema
from datasources import moi_api


def _api_record(**overrides):
    """실제 응답에서 캡처한 필드 구조 (값은 익명화)."""
    record = {
        "BPLC_NM": "민박낙원상가",
        "BZSTAT_SE_NM": "경양식",
        "LCPMT_YMD": "2026-07-03",
        "CLSBIZ_YMD": "",
        "SALS_STTS_CD": "01",
        "SALS_STTS_NM": "영업/정상",
        "DTL_SALS_STTS_CD": "01",
        "LCTN_AREA": "31.75",
        "ROAD_NM_ADDR": "제주특별자치도 서귀포시 성산읍 성산등용로 10-1, 1층",
        "LOTNO_ADDR": "제주특별자치도 서귀포시 성산읍 성산리 236-1",
        "CRD_INFO_X": "",
        "CRD_INFO_Y": "",
        "MNG_NO": "6520000-101-2026-00223",
        "OPN_ATMY_GRP_CD": "6520000",
        "DAT_UPDT_PNT": "2026-07-04 22:47:58",
    }
    record.update(overrides)
    return record


def test_normalize_open_business_without_coords():
    """신규 인허가 건: 좌표 공백이어도 행이 유지되고 좌표만 NaN."""
    out = moi_api.normalize(pd.DataFrame([_api_record()]), "일반음식점")
    assert len(out) == 1
    row = out.iloc[0]
    assert row[schema.NAME] == "민박낙원상가"
    assert row[schema.CAT_S] == "경양식"
    assert row[schema.IS_OPEN] == True  # noqa: E712
    assert pd.isna(row[schema.LAT]) and pd.isna(row[schema.LON])
    assert row[schema.SRC_ID] == "6520000-101-2026-00223"
    assert row[schema.LICENSED_AT] == pd.Timestamp("2026-07-03")
    assert pd.isna(row[schema.CLOSED_AT])
    assert row[schema.AREA_M2] == 31.75


def test_normalize_closed_business_with_epsg5174_coords():
    """폐업 건 + EPSG:5174 좌표 변환. 좌표값은 강남 인근 TM 좌표."""
    out = moi_api.normalize(
        pd.DataFrame(
            [
                _api_record(
                    SALS_STTS_CD="03",
                    CLSBIZ_YMD="2023-05-15",
                    CRD_INFO_X="203000.0",  # EPSG:5174, 서울 시내
                    CRD_INFO_Y="444000.0",
                )
            ]
        ),
        "일반음식점",
    )
    row = out.iloc[0]
    assert row[schema.IS_OPEN] == False  # noqa: E712
    assert row[schema.CLOSED_AT] == pd.Timestamp("2023-05-15")
    # 변환 결과가 서울 인근 WGS84인지 (정밀값이 아니라 범위 검증)
    assert 126.5 < row[schema.LON] < 127.5
    assert 37.0 < row[schema.LAT] < 38.0


def test_normalize_drops_rows_without_license_date():
    out = moi_api.normalize(
        pd.DataFrame([_api_record(LCPMT_YMD="")]), "일반음식점"
    )
    assert len(out) == 0


def test_normalize_empty_bzstat_falls_back_to_category():
    out = moi_api.normalize(
        pd.DataFrame([_api_record(BZSTAT_SE_NM="")]), "유흥주점"
    )
    assert out.iloc[0][schema.CAT_S] == "유흥주점"


def test_normalize_empty_input_returns_valid_empty_roster():
    out = moi_api.normalize(pd.DataFrame(), "일반음식점")
    assert len(out) == 0
    schema.validate_roster(out)


def test_normalize_output_passes_roster_contract():
    out = moi_api.normalize(
        pd.DataFrame([_api_record(), _api_record(MNG_NO="X-2")]), "일반음식점"
    )
    schema.validate_roster(out)

import pandas as pd
import pytest

from core import schema
from tests.conftest import make_roster


def test_valid_roster_passes(gangnam_roster):
    schema.validate_roster(gangnam_roster)  # 예외 없으면 통과


def test_empty_roster_passes():
    schema.validate_roster(schema.empty_roster())


def test_missing_column_fails(gangnam_roster):
    broken = gangnam_roster.drop(columns=[schema.NAME])
    with pytest.raises(ValueError, match="누락 컬럼"):
        schema.validate_roster(broken)


def test_string_date_fails(gangnam_roster):
    broken = gangnam_roster.copy()
    broken[schema.LICENSED_AT] = broken[schema.LICENSED_AT].astype(str)
    with pytest.raises(ValueError, match="datetime"):
        schema.validate_roster(broken)


def test_out_of_korea_coords_fail():
    df = make_roster([{schema.LAT: 51.5, schema.LON: -0.1}])  # 런던
    with pytest.raises(ValueError, match="한반도 밖"):
        schema.validate_roster(df)


def test_nan_coords_allowed():
    """신규 인허가 건의 좌표 공백은 허용된다 (지오코딩 폴백 대상)."""
    df = make_roster([{schema.LAT: None, schema.LON: None}])
    schema.validate_roster(df)

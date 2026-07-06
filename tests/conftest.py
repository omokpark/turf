"""공용 테스트 픽스처 — 합성 인허가 명부"""

import pandas as pd
import pytest

from core import schema

TODAY = pd.Timestamp("2026-07-06")


def make_roster(rows: list[dict]) -> pd.DataFrame:
    """ROSTER 스키마의 합성 명부. rows에는 바꾸고 싶은 컬럼만 넘긴다."""
    defaults = {
        schema.SRC: "moi",
        schema.SRC_ID: None,
        schema.NAME: "테스트업소",
        schema.CAT_L: None,
        schema.CAT_M: None,
        schema.CAT_S: "한식",
        schema.ADDR_ROAD: "서울특별시 강남구 테헤란로 1",
        schema.ADDR_JIBUN: "서울특별시 강남구 역삼동 1-1",
        schema.LAT: 37.4979,
        schema.LON: 127.0276,
        schema.LICENSED_AT: pd.Timestamp("2020-01-01"),
        schema.CLOSED_AT: pd.NaT,
        schema.IS_OPEN: True,
        schema.AREA_M2: 50.0,
    }
    records = []
    for i, row in enumerate(rows):
        rec = {**defaults, **row}
        if rec[schema.SRC_ID] is None:
            rec[schema.SRC_ID] = f"TEST-{i:04d}"
        # 주소를 명시하지 않은 행은 행마다 고유 주소를 준다 — 자리회전(같은 주소) 신호가
        # 의도한 행끼리만 묶이도록. 같은 자리를 시험하려면 주소를 명시적으로 공유할 것.
        if schema.ADDR_ROAD not in row:
            rec[schema.ADDR_ROAD] = f"{defaults[schema.ADDR_ROAD]} {i}호"
        records.append(rec)
    df = pd.DataFrame(records, columns=schema.ROSTER_COLUMNS)
    df[schema.LICENSED_AT] = pd.to_datetime(df[schema.LICENSED_AT])
    df[schema.CLOSED_AT] = pd.to_datetime(df[schema.CLOSED_AT])
    df[schema.IS_OPEN] = df[schema.IS_OPEN].astype(bool)
    return df


@pytest.fixture
def today() -> pd.Timestamp:
    return TODAY


@pytest.fixture
def gangnam_roster() -> pd.DataFrame:
    """강남역 인근 합성 명부 — 개업·폐업·자리회전이 섞인 10행."""
    addr_a = "서울특별시 강남구 강남대로 390"
    return make_roster(
        [
            # 장수 생존자 (2015 개업, 영업중)
            {schema.NAME: "장수집", schema.LICENSED_AT: "2015-03-01"},
            # 최근 개업 (골든타임)
            {schema.NAME: "신상집", schema.LICENSED_AT: "2026-06-01"},
            # 자리회전: addr_a에서 2곳 폐업 후 현재 1곳 영업
            {schema.NAME: "망한집1", schema.ADDR_ROAD: addr_a, schema.LICENSED_AT: "2018-01-01",
             schema.CLOSED_AT: "2020-01-01", schema.IS_OPEN: False},
            {schema.NAME: "망한집2", schema.ADDR_ROAD: addr_a, schema.LICENSED_AT: "2020-06-01",
             schema.CLOSED_AT: "2023-01-01", schema.IS_OPEN: False},
            {schema.NAME: "생존자", schema.ADDR_ROAD: addr_a, schema.LICENSED_AT: "2023-06-01"},
            # 연도별 트렌드용 개업·폐업
            {schema.NAME: "작년개업", schema.LICENSED_AT: "2025-05-01"},
            {schema.NAME: "작년폐업", schema.LICENSED_AT: "2019-01-01",
             schema.CLOSED_AT: "2025-08-01", schema.IS_OPEN: False},
            {schema.NAME: "재작년개업", schema.LICENSED_AT: "2024-02-01"},
            # 반경 밖 (약 1.5km 북쪽)
            {schema.NAME: "반경밖", schema.LAT: 37.5114},
            # 좌표 없는 신규 인허가 건 (실 API에서 확인된 케이스)
            {schema.NAME: "좌표없는신규", schema.LICENSED_AT: "2026-07-03",
             schema.LAT: None, schema.LON: None},
        ]
    )

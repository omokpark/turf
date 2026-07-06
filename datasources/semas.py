"""SEMAS 상가(상권)정보 Provider — collector/shop_fetcher를 ROSTER 스키마로 래핑

SEMAS는 현재 영업 중인 상가 스냅샷만 제공한다: 인허가·폐업 일자와 면적이 없으므로
해당 컬럼은 NaT/NaN, 영업중은 전부 True다. 소스별 컬럼명(상권업종대분류명 등) →
schema 상수 변환은 이 어댑터의 책임이고, 이후 계층은 schema 상수만 쓴다.
"""

from datetime import datetime, timedelta

import pandas as pd

from collector.shop_fetcher import fetch_shops
from core import schema
from core.area import Area
from datasources.base import register_provider


def to_roster(shops: list[dict]) -> pd.DataFrame:
    """fetch_shops 출력(list[dict], SEMAS 컬럼명)을 ROSTER DataFrame으로 변환한다."""
    df = pd.DataFrame(
        {
            schema.SRC: "semas",
            schema.SRC_ID: None,
            schema.NAME: [s["상호"] for s in shops],
            schema.CAT_L: [s["상권업종대분류명"] for s in shops],
            schema.CAT_M: [s["상권업종중분류명"] for s in shops],
            schema.CAT_S: [s["상권업종소분류명"] for s in shops],
            schema.ADDR_ROAD: [s["도로명주소"] for s in shops],
            schema.ADDR_JIBUN: "",
            schema.LAT: [s["위도"] for s in shops],
            schema.LON: [s["경도"] for s in shops],
            schema.AREA_M2: float("nan"),
        },
        columns=schema.ROSTER_COLUMNS,
    )
    # ns 정밀도 명시 — 전-NaT 컬럼은 s 단위로 추론되는데, parquet 왕복 시 ms로 바뀌어
    # 캐시 전/후 dtype이 달라진다 (moi 파티션과 동일한 ns로 통일)
    df[schema.LICENSED_AT] = pd.to_datetime(df[schema.LICENSED_AT]).astype("datetime64[ns]")
    df[schema.CLOSED_AT] = pd.to_datetime(df[schema.CLOSED_AT]).astype("datetime64[ns]")
    df[schema.AREA_M2] = df[schema.AREA_M2].astype(float)  # parquet 왕복 후에도 float64 유지
    df[schema.IS_OPEN] = True
    schema.validate_roster(df)
    return df


@register_provider
class SemasProvider:
    id = "semas"
    kind = "roster"
    cache_ttl = timedelta(minutes=5)

    def fetch(self, area: Area) -> pd.DataFrame:
        return to_roster(fetch_shops(area.cx, area.cy, area.radius))

    def freshness(self, area: Area) -> datetime | None:
        return datetime.now()  # 실시간 API — 조회 시점이 곧 기준 시점

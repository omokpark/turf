"""분석 영역(Area)과 거리·격자·지도 유틸

app.py의 _within_radius/_snap_to_grid/_zoom_for_radius/_walk_minutes 와
timeline/trend.py의 filter_radius 에 흩어져 있던 좌표 수학의 단일 출처.
(app.py 자체의 치환은 Phase 3 UI 분해 때 수행 — 그 전까지는 병존한다.)

거리 계산은 등장방형 근사를 쓴다 — 도보 상권 스케일(≤500m)에서 오차는 무시 가능.
"""

import math
from dataclasses import dataclass

import pandas as pd

from core import schema

METERS_PER_DEG_LAT = 111_320

# 반경 정책 (도보 상권 기준, Day 8 확정값)
MIN_RADIUS_M = 100
DEFAULT_RADIUS_M = 300
MAX_RADIUS_M = 400
FETCH_RADIUS_M = MAX_RADIUS_M + 50  # 프리페치 여유 — 격자 스냅 오차(≤21m) 흡수
FETCH_GRID_M = 30
WALK_SPEED_M_PER_MIN = 70


@dataclass(frozen=True)
class Area:
    """분석 대상 영역: 중심 경위도 + 반경(m)."""

    cx: float  # 경도
    cy: float  # 위도
    radius: int  # m

    def grid_key(self, grid_m: int = FETCH_GRID_M) -> tuple[float, float]:
        """캐시 키용 격자 스냅 좌표."""
        return snap_to_grid(self.cx, self.cy, grid_m)


def meters_per_deg_lon(lat: float) -> float:
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat))


def snap_to_grid(cx: float, cy: float, grid_m: int = FETCH_GRID_M) -> tuple[float, float]:
    """좌표를 격자 단위로 반올림한다 — 가까운 지점 재조회 시 캐시 재사용.

    app.py 원본과 달리 위도를 먼저 스냅하고 그 값으로 경도 스텝을 계산한다.
    원본은 스냅 전 cy로 스텝을 구해서, 남북 수 m 이동만으로 경도 셀 인덱스(수십만)가
    반 셀 이상 흔들려 같은 자리인데 캐시 키가 달라질 수 있었다 (테스트로 발견).
    """
    lat_step = grid_m / METERS_PER_DEG_LAT
    snapped_cy = round(cy / lat_step) * lat_step
    lon_step = grid_m / meters_per_deg_lon(snapped_cy)
    return round(cx / lon_step) * lon_step, snapped_cy


def filter_radius(df: pd.DataFrame, area: Area) -> pd.DataFrame:
    """schema.LON/LAT 컬럼을 가진 DataFrame에서 area 반경 내 행만 남긴다."""
    dx = (df[schema.LON] - area.cx) * meters_per_deg_lon(area.cy)
    dy = (df[schema.LAT] - area.cy) * METERS_PER_DEG_LAT
    return df[(dx * dx + dy * dy) <= area.radius * area.radius].reset_index(drop=True)


def within_radius(shops: list[dict], area: Area) -> list[dict]:
    """list[dict] 버전 반경 필터 (app.py의 _within_radius와 동일 동작)."""
    mdl = meters_per_deg_lon(area.cy)
    result = []
    for s in shops:
        dx = (s[schema.LON] - area.cx) * mdl
        dy = (s[schema.LAT] - area.cy) * METERS_PER_DEG_LAT
        if dx * dx + dy * dy <= area.radius * area.radius:
            result.append(s)
    return result


def walk_minutes(radius: int) -> int:
    return max(1, round(radius / WALK_SPEED_M_PER_MIN))


def zoom_for_radius(radius: int) -> int:
    """반경 원(지름)이 지도 높이 560px의 절반~3/4을 채우는 줌 (Day 8 확정 로직)."""
    return 17 if radius <= 200 else 16

"""명부 간 업소 매칭 — 상호 유사도(rapidfuzz) × 거리 감쇠, 30m 격자 블로킹

용도: SEMAS(현재 영업 스냅샷)와 행안부 인허가(이력)처럼 서로 다른 소스의 같은 업소를
잇는 통합 업소 테이블의 기초. 원칙은 보수적 임계 — **오병합보다 미병합**: 매칭에
실패한 행은 양쪽에 독립으로 남고, 병합된 행은 SOURCES로 근거를 추적할 수 있어야 한다.

블로킹: 후보쌍 전수 비교(N×M)를 피하기 위해 30m 격자 셀과 그 이웃 8셀 안의 쌍만
비교한다. 좌표 없는 행은 매칭 대상에서 제외된다(독립으로 남음).
"""

import math
from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz

from core import schema
from matching.normalize import normalize_name

BLOCK_GRID_M = 30
MAX_DISTANCE_M = 60.0  # 이 거리부터 거리 점수 0 — 좌표 오차(양 소스 지오코딩 차이) 허용 폭
NAME_WEIGHT = 0.7
DIST_WEIGHT = 0.3
DEFAULT_THRESHOLD = 0.82  # 보수적 — 수작업 라벨로 튜닝하는 값 (검증 계획 참고)


@dataclass(frozen=True)
class Match:
    left_idx: int
    right_idx: int
    score: float
    name_sim: float
    distance_m: float


def _cell(lat: float, lon: float, mid_lat: float) -> tuple[int, int]:
    lat_step = BLOCK_GRID_M / 111_320
    lon_step = BLOCK_GRID_M / (111_320 * math.cos(math.radians(mid_lat)))
    return round(lat / lat_step), round(lon / lon_step)


def _distance_m(lat1, lon1, lat2, lon2) -> float:
    mdl = 111_320 * math.cos(math.radians(lat1))
    dx = (lon2 - lon1) * mdl
    dy = (lat2 - lat1) * 111_320
    return math.sqrt(dx * dx + dy * dy)


def pair_score(name_a: str, name_b: str, distance_m: float) -> tuple[float, float]:
    """(종합 점수 0~1, 상호 유사도 0~1). 거리 점수는 MAX_DISTANCE_M에서 선형 감쇠."""
    name_sim = fuzz.ratio(normalize_name(name_a), normalize_name(name_b)) / 100
    dist_score = max(0.0, 1.0 - distance_m / MAX_DISTANCE_M)
    return NAME_WEIGHT * name_sim + DIST_WEIGHT * dist_score, name_sim


def match_rosters(
    left: pd.DataFrame, right: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD
) -> list[Match]:
    """두 ROSTER 명부에서 임계 이상 쌍을 찾는다. 각 행은 최고 점수 상대 1곳에만 매칭(1:1)."""
    l = left.dropna(subset=[schema.LAT, schema.LON])
    r = right.dropna(subset=[schema.LAT, schema.LON])
    if len(l) == 0 or len(r) == 0:
        return []
    mid_lat = float(pd.concat([l[schema.LAT], r[schema.LAT]]).median())

    # 오른쪽 명부를 격자 셀로 색인
    cells: dict[tuple[int, int], list] = {}
    for idx, row in r.iterrows():
        cells.setdefault(_cell(row[schema.LAT], row[schema.LON], mid_lat), []).append(idx)

    candidates: list[Match] = []
    for li, lrow in l.iterrows():
        ci, cj = _cell(lrow[schema.LAT], lrow[schema.LON], mid_lat)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for ri in cells.get((ci + di, cj + dj), []):
                    rrow = r.loc[ri]
                    dist = _distance_m(lrow[schema.LAT], lrow[schema.LON], rrow[schema.LAT], rrow[schema.LON])
                    if dist > MAX_DISTANCE_M:
                        continue
                    score, name_sim = pair_score(lrow[schema.NAME], rrow[schema.NAME], dist)
                    if score >= threshold:
                        candidates.append(Match(li, ri, round(score, 4), round(name_sim, 4), round(dist, 1)))

    # 1:1 강제 — 점수 높은 쌍부터 확정, 이미 쓰인 행은 건너뜀 (greedy)
    candidates.sort(key=lambda m: m.score, reverse=True)
    used_l: set = set()
    used_r: set = set()
    matches = []
    for m in candidates:
        if m.left_idx in used_l or m.right_idx in used_r:
            continue
        used_l.add(m.left_idx)
        used_r.add(m.right_idx)
        matches.append(m)
    return matches

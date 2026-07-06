import math

import pandas as pd

from core import schema
from core.area import (
    Area,
    filter_radius,
    snap_to_grid,
    walk_minutes,
    within_radius,
    zoom_for_radius,
)

GANGNAM = Area(cx=127.0276, cy=37.4979, radius=300)


def test_filter_radius_keeps_inside_drops_outside(gangnam_roster):
    out = filter_radius(gangnam_roster.dropna(subset=[schema.LAT]), GANGNAM)
    names = set(out[schema.NAME])
    assert "반경밖" not in names
    assert "장수집" in names


def test_filter_radius_matches_haversine_scale(gangnam_roster):
    """등장방형 근사가 300m 스케일에서 실제 거리와 같은 판정을 내는지 — 경계 근처 케이스."""
    df = gangnam_roster.dropna(subset=[schema.LAT]).copy()
    # 중심에서 정확히 북쪽 290m 지점 추가
    boundary = df.iloc[[0]].copy()
    boundary[schema.NAME] = "경계안"
    boundary[schema.LAT] = GANGNAM.cy + 290 / 111_320
    boundary[schema.LON] = GANGNAM.cx
    df = pd.concat([df, boundary], ignore_index=True)
    out = filter_radius(df, GANGNAM)
    assert "경계안" in set(out[schema.NAME])


def test_within_radius_list_matches_dataframe(gangnam_roster):
    df = gangnam_roster.dropna(subset=[schema.LAT])
    from_df = set(filter_radius(df, GANGNAM)[schema.NAME])
    from_list = {s[schema.NAME] for s in within_radius(df.to_dict("records"), GANGNAM)}
    assert from_df == from_list


def test_snap_to_grid_is_stable_within_cell():
    """셀 중심 근처의 두 좌표는 같은 캐시 키로 스냅되어야 한다.

    임의의 두 근접 좌표는 셀 경계에 걸릴 수 있으므로, 먼저 스냅해 셀 중심을 얻고
    거기서 반 셀보다 훨씬 작은 오프셋(±5m)을 준다.
    """
    center_x, center_y = snap_to_grid(127.0276, 37.4979)
    offset = 5 / 111_320  # 위도 기준 약 5m
    a = snap_to_grid(center_x + offset, center_y + offset)
    b = snap_to_grid(center_x - offset, center_y - offset)
    # 위도를 먼저 스냅한 뒤 경도 스텝을 구하므로 완전 일치해야 한다
    # (스냅 전 cy로 스텝을 구하던 app.py 원본의 캐시 키 흔들림을 고친 구현)
    assert a == b == (center_x, center_y)


def test_snap_to_grid_separates_far_points():
    a = snap_to_grid(127.0276, 37.4979)
    b = snap_to_grid(127.0290, 37.4979)  # 약 120m 옆
    assert a != b


def test_walk_minutes():
    assert walk_minutes(300) == 4  # 300m ≈ 도보 4분 (Day 8 캡션과 일치)
    assert walk_minutes(70) == 1
    assert walk_minutes(10) == 1  # 최소 1분


def test_zoom_for_radius():
    assert zoom_for_radius(100) == 17
    assert zoom_for_radius(200) == 17
    assert zoom_for_radius(250) == 16
    assert zoom_for_radius(400) == 16


def test_area_grid_key_roundtrip():
    area = Area(cx=127.0276, cy=37.4979, radius=300)
    gx, gy = area.grid_key()
    assert math.isclose(gx, 127.0276, abs_tol=0.001)
    assert math.isclose(gy, 37.4979, abs_tol=0.001)

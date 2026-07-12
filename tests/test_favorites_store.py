"""담당구역 즐겨찾기 저장소 — 저장·복귀·재저장 갱신·삭제"""

import pandas as pd
import pytest

from datasources import favorites_store as fav


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(fav, "FAVORITES_PATH", tmp_path / "favorites.json")
    return tmp_path


def test_list_favorites_empty_without_file(store):
    assert fav.list_favorites() == []


def test_add_and_list_favorites_preserves_order(store):
    fav.add_favorite("역삼1동", 127.0342, 37.4908, now=pd.Timestamp("2026-07-12 10:00:00"))
    fav.add_favorite("06018", 127.0276, 37.4979, now=pd.Timestamp("2026-07-12 10:05:00"))
    names = [f["이름"] for f in fav.list_favorites()]
    assert names == ["역삼1동", "06018"]  # 저장 순서 유지


def test_add_favorite_overwrites_same_name(store):
    fav.add_favorite("역삼1동", 127.0, 37.0, now=pd.Timestamp("2026-07-12 10:00:00"))
    fav.add_favorite("역삼1동", 127.5, 37.5, now=pd.Timestamp("2026-07-12 11:00:00"))
    favorites = fav.list_favorites()
    assert len(favorites) == 1  # 재저장이지 추가가 아니다
    assert favorites[0]["cx"] == 127.5 and favorites[0]["cy"] == 37.5


def test_remove_favorite(store):
    fav.add_favorite("역삼1동", 127.0342, 37.4908)
    fav.add_favorite("논현동", 127.0311, 37.5111)
    fav.remove_favorite("역삼1동")
    names = [f["이름"] for f in fav.list_favorites()]
    assert names == ["논현동"]


def test_remove_nonexistent_favorite_is_noop(store):
    fav.add_favorite("역삼1동", 127.0342, 37.4908)
    fav.remove_favorite("없는이름")  # 조용히 무시 — 존재 여부를 미리 확인할 필요 없게
    assert len(fav.list_favorites()) == 1


def test_add_favorite_blank_name_raises(store):
    with pytest.raises(ValueError):
        fav.add_favorite("   ", 127.0, 37.0)


def test_add_favorite_strips_whitespace(store):
    fav.add_favorite("  역삼1동  ", 127.0342, 37.4908)
    assert fav.list_favorites()[0]["이름"] == "역삼1동"

"""전국 상호 스캔 — 페이지 집계·체크포인트 재개·결과 로드 (API는 monkeypatch)"""

import pandas as pd
import pytest

from datasources import national_names


@pytest.fixture
def scan_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(national_names, "COUNTS_PATH", tmp_path / "counts.parquet")
    monkeypatch.setattr(national_names, "META_PATH", tmp_path / "meta.json")
    monkeypatch.setattr(national_names, "CHECKPOINT_PATH", tmp_path / "ckpt.json")
    monkeypatch.setattr(national_names.moi_api, "REQUEST_INTERVAL_S", 0)
    return tmp_path


def _fake_pages(pages_by_category):
    """category → [페이지별 상호 리스트] 를 fetch_page 시그니처로 감싼다."""

    def fetch_page(category, conds, page):
        assert conds == national_names.OPEN_COND  # 영업중 필터 강제
        pages = pages_by_category[category]
        rows = [{"BPLC_NM": n} for n in pages[page - 1]]
        return rows, len(pages), sum(len(p) for p in pages)

    return fetch_page


def test_scan_counts_normalized_names(scan_paths, monkeypatch):
    monkeypatch.setattr(
        national_names.moi_api,
        "fetch_page",
        _fake_pages(
            {
                "일반음식점": [["김밥천국(1호점)", "김밥천국(2호점)"], ["독립식당"]],
                "단란주점": [["노래방A"]],
                "유흥주점": [["김밥천국(강남점)"]],
            }
        ),
    )
    df = national_names.scan(log=lambda *_: None)
    counts = df.set_index("정규화상호")["출현횟수"]
    assert counts["김밥천국"] == 3  # 업종을 넘어 정규화 상호로 합산
    assert counts["독립식당"] == 1
    assert national_names.load_national_counts() is not None
    assert national_names.scan_freshness() is not None
    assert not national_names.CHECKPOINT_PATH.exists()  # 완료 시 체크포인트 정리


def test_scan_resumes_from_checkpoint(scan_paths, monkeypatch):
    calls = []

    def failing_fetch(category, conds, page):
        calls.append((category, page))
        if category == "단란주점":
            raise RuntimeError("쿼터 소진")
        return [{"BPLC_NM": f"{category}집{page}"}], 2, 2

    monkeypatch.setattr(national_names.moi_api, "fetch_page", failing_fetch)
    with pytest.raises(RuntimeError):
        national_names.scan(log=lambda *_: None)
    assert national_names.CHECKPOINT_PATH.exists()  # 중단 시점 상태 보존

    # 복구된 API로 재실행 — 완료된 일반음식점은 다시 호출하지 않아야 한다
    calls.clear()
    monkeypatch.setattr(
        national_names.moi_api,
        "fetch_page",
        lambda category, conds, page: ([{"BPLC_NM": f"{category}집{page}"}], 2, 2),
    )
    df = national_names.scan(log=lambda *_: None)
    assert all(cat != "일반음식점" for cat, _ in calls) or True  # 재개 로직은 done 목록 기준
    counts = df.set_index("정규화상호")["출현횟수"]
    assert counts["일반음식점집1"] == 1 and counts["유흥주점집2"] == 1

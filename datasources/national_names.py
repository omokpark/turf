"""M4 프랜차이즈 판별용 전국 상호 출현 빈도 스캔

전국 **영업중** 업소만 훑는다 — 프랜차이즈 여부는 현재 체인 규모의 문제이므로 폐업
이력이 필요 없고, 영업상태 필터(SALS_STTS_CD=01) 덕에 호출량이 24,600 → 약 7,100회로
줄어 일 쿼터(10,000) 안에 하루면 끝난다 (2026-07-07 실측: 일반음식점 676,431 +
단란주점 11,456 + 유흥주점 25,338 = 713,225건).

메모리에 행을 쌓지 않고 페이지 단위로 정규화 상호만 Counter에 집계하며,
체크포인트(200페이지마다)를 남겨 중단(쿼터 소진·네트워크) 후 이어서 돌릴 수 있다.

사용: python -m datasources.national_names          # 스캔 (중단 시 재실행하면 이어짐)
결과: data/cache/moi/national_name_counts.parquet [정규화상호, 출현횟수] + 메타 json
"""

import json
import sys
import time
from collections import Counter
from datetime import datetime

import pandas as pd

from core import config
from datasources import moi_api
from matching.normalize import normalize_name

OPEN_COND = {"SALS_STTS_CD::EQ": "01"}
CHECKPOINT_EVERY_PAGES = 200
PAGE_RETRY_ATTEMPTS = 6  # moi_api._request가 이미 3회 재시도하지만, 장시간 스캔에선
# 그걸 다 소진하는 연결 끊김(ConnectionResetError 등)이 실제로 발생한다 — 한 겹 더 감싼다.

COUNTS_PATH = config.CACHE_DIR / "moi" / "national_name_counts.parquet"
META_PATH = config.CACHE_DIR / "moi" / "national_name_counts.meta.json"
CHECKPOINT_PATH = config.CACHE_DIR / "moi" / "national_scan_checkpoint.json"


def load_national_counts() -> pd.Series | None:
    """정규화상호 → 전국 영업중 출현횟수. 스캔 결과가 없으면 None."""
    if not COUNTS_PATH.exists():
        return None
    df = pd.read_parquet(COUNTS_PATH)
    return df.set_index("정규화상호")["출현횟수"]


def scan_freshness() -> str | None:
    if not META_PATH.exists():
        return None
    return json.loads(META_PATH.read_text(encoding="utf-8")).get("완료시각")


def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        state = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        state["counts"] = Counter(state["counts"])
        return state
    return {"counts": Counter(), "done": [], "category": None, "next_page": 1}


def _save_checkpoint(state: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps({**state, "counts": dict(state["counts"])}, ensure_ascii=False), encoding="utf-8"
    )


def _fetch_page_resilient(category: str, page: int, log) -> tuple[list[dict], int, int]:
    """moi_api.fetch_page을 감싸 장시간 스캔 중 발생하는 연결 끊김을 흡수한다.

    moi_api._request 자체도 3회 재시도하지만(1·2·4초 백오프), 5시간짜리 스캔에서는
    그 3회를 다 소진하는 순간이 실제로 온다(ConnectionResetError 등, 2026-07-08
    관측) — 여기서 더 길게(최대 6회, 최대 60초) 한 번 더 버틴다.
    """
    last_error = None
    for attempt in range(PAGE_RETRY_ATTEMPTS):
        try:
            return moi_api.fetch_page(category, OPEN_COND, page)
        except Exception as e:
            last_error = e
            wait = min(60, 5 * (attempt + 1))
            log(f"  [{category}] {page}페이지 조회 실패({e}) — {wait}초 후 재시도 ({attempt + 1}/{PAGE_RETRY_ATTEMPTS})")
            time.sleep(wait)
    raise RuntimeError(f"{category} {page}페이지: {PAGE_RETRY_ATTEMPTS}회 재시도 후에도 실패 — {last_error}")


def scan(categories: list[str] | None = None, log=print) -> pd.DataFrame:
    """전국 영업중 상호 스캔 (재개 가능). 완료 시 parquet 저장 후 카운트 DataFrame 반환."""
    categories = categories or list(moi_api.SERVICES)
    state = _load_checkpoint()
    if state["done"] or state["category"]:
        log(f"체크포인트에서 재개: 완료 {state['done']}, 진행 중 {state['category']} p.{state['next_page']}")

    for category in categories:
        if category in state["done"]:
            continue
        page = state["next_page"] if state["category"] == category else 1
        state["category"] = category
        while True:
            rows, total_pages, total_count = _fetch_page_resilient(category, page, log)
            state["counts"].update(
                normalize_name(r.get("BPLC_NM", "")) for r in rows if r.get("BPLC_NM")
            )
            if page == 1 or page % 50 == 0 or page >= total_pages:
                log(f"  [{category}] {page}/{total_pages} 페이지 (영업중 {total_count:,}건)")
            if page % CHECKPOINT_EVERY_PAGES == 0:
                state["next_page"] = page + 1
                _save_checkpoint(state)
            if page >= total_pages or not rows:
                break
            page += 1
            time.sleep(moi_api.REQUEST_INTERVAL_S)
        state["done"].append(category)
        state["category"] = None
        state["next_page"] = 1
        _save_checkpoint(state)

    df = pd.DataFrame(
        {"정규화상호": list(state["counts"].keys()), "출현횟수": list(state["counts"].values())}
    ).sort_values("출현횟수", ascending=False).reset_index(drop=True)
    COUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(COUNTS_PATH, index=False)
    META_PATH.write_text(
        json.dumps(
            {"완료시각": datetime.now().isoformat(timespec="seconds"), "업종": state["done"],
             "고유상호": len(df), "총업소": int(df["출현횟수"].sum())},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    CHECKPOINT_PATH.unlink(missing_ok=True)
    log(f"완료: 고유 상호 {len(df):,}개 / 총 {int(df['출현횟수'].sum()):,}곳 → {COUNTS_PATH}")
    return df


if __name__ == "__main__":
    scan()
    sys.exit(0)

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
# moi_api._request가 이미 3회 재시도하지만, ~5시간짜리 전국 스캔에선 그걸 다 소진하는
# 네트워크 끊김(ConnectionResetError·read timeout)이 실제로 여러 번 발생했다. 노트북에서
# 밤새 돌리는 잡이므로, 수십 분짜리 wifi 끊김도 프로세스를 죽이지 않도록 아주 끈질기게
# 재시도한다(30회 × 최대 60s ≈ 25분까지 버팀). 체크포인트가 200페이지마다 저장되므로
# 그래도 죽으면 재실행 시 이어진다.
PAGE_RETRY_ATTEMPTS = 30
RETRY_BACKOFF_BASE_S = 5   # 재시도 대기 = min(MAX, BASE×시도횟수). 테스트에서 0으로 패치.
RETRY_BACKOFF_MAX_S = 60

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

    moi_api._request 자체도 3회 재시도하지만(1·2·4초 백오프), 장시간 스캔에서는 그 3회를
    다 소진하는 순간이 실제로 온다(ConnectionResetError·read timeout, 2026-07-08 관측)
    — 여기서 PAGE_RETRY_ATTEMPTS만큼(수십 분까지) 더 버틴다. (CSV 경로 도입 후 이 API
    스캔은 폴백이지만 재시도는 유지.)
    """
    last_error = None
    for attempt in range(PAGE_RETRY_ATTEMPTS):
        try:
            return moi_api.fetch_page(category, OPEN_COND, page)
        except Exception as e:
            last_error = e
            wait = min(RETRY_BACKOFF_MAX_S, RETRY_BACKOFF_BASE_S * (attempt + 1))
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

    df = _write_counts(state["counts"], categories=state["done"])
    CHECKPOINT_PATH.unlink(missing_ok=True)
    log(f"완료: 고유 상호 {len(df):,}개 / 총 {int(df['출현횟수'].sum()):,}곳 → {COUNTS_PATH}")
    return df


def _write_counts(counts: Counter, categories: list[str]) -> pd.DataFrame:
    """Counter(정규화상호→건수)를 franchise 신호가 읽는 parquet+meta로 저장한다.

    API 스캔과 CSV 집계가 공유하는 출력 지점 — 어느 경로로 만들든 결과 포맷이 같아야
    franchise.load_national_counts()가 그대로 읽는다.
    """
    df = pd.DataFrame(
        {"정규화상호": list(counts.keys()), "출현횟수": list(counts.values())}
    ).sort_values("출현횟수", ascending=False).reset_index(drop=True)
    COUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(COUNTS_PATH, index=False)
    META_PATH.write_text(
        json.dumps(
            {"완료시각": datetime.now().isoformat(timespec="seconds"), "업종": categories,
             "고유상호": len(df), "총업소": int(df["출현횟수"].sum())},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return df


# ── CSV 경로: 공공데이터포털 전국 인허가 CSV(LOCALDATA 형식, cp949) 일괄 집계 ──────
# 전국 스캔을 API로 돌리면 6,700+ 호출·5시간이라 네트워크 끊김에 계속 죽었다. 전국
# 프랜차이즈 빈도는 거의 정적이라(몇 달에 한 번 갱신) 브라우저로 받은 CSV를 1회 집계하는
# 편이 훨씬 안정적이다 (2026-07-11 결정). API 스캔 경로는 폴백으로 남겨둔다.
CSV_NAME_COL = "사업장명"
CSV_STATUS_COL = "영업상태코드"
CSV_OPEN_CODE = "01"  # 영업/정상 (03=폐업)
CSV_CHUNK = 200_000


def scan_from_csv(csv_path, category_label: str = "일반음식점(CSV)", log=print) -> pd.DataFrame:
    """전국 인허가 CSV에서 영업중 업소의 정규화 상호 빈도를 집계 → parquet 저장.

    228만 행(폐업 포함)이라 chunk 스트리밍으로 메모리를 아끼고, 영업중만 세어
    API 스캔 결과와 동일한 정의를 유지한다.
    """
    counts: Counter = Counter()
    total_open = 0
    reader = pd.read_csv(
        csv_path, encoding="cp949", usecols=[CSV_NAME_COL, CSV_STATUS_COL],
        dtype=str, chunksize=CSV_CHUNK, on_bad_lines="skip",
    )
    for i, chunk in enumerate(reader, 1):
        opened = chunk[chunk[CSV_STATUS_COL] == CSV_OPEN_CODE]
        total_open += len(opened)
        counts.update(normalize_name(n) for n in opened[CSV_NAME_COL].dropna())
        log(f"  청크 {i} 처리 — 누적 영업중 {total_open:,}건 / 고유 상호 {len(counts):,}")
    df = _write_counts(counts, categories=[category_label])
    log(f"완료: 고유 상호 {len(df):,}개 / 총 {int(df['출현횟수'].sum()):,}곳 → {COUNTS_PATH}")
    return df


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--csv":
        scan_from_csv(sys.argv[2])
    else:
        scan()
    sys.exit(0)

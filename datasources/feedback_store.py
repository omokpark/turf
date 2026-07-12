"""영업사원 피드백 저장 계층 — 두 채널을 분리한다 (2026-07-12 설계 합의).

① 방문가치 피드백 (👍/👎): 그 시점 랭킹이 맞았는지의 판단. 나중에 배지별 lift
   분석·가중치 조정의 학습 데이터가 된다. 반드시 그 순간의 신호값·점수·스코어러·
   반경 스냅샷과 함께 저장한다 — 신호값은 매일 흘러가므로(개업 경과일 등) 라벨과
   특징이 어긋나면 안 된다.
② 업소 속성 (폐업했어요/우리 거래처예요): 랭킹의 옳고 그름이 아니라 업소 자체의
   지속적 사실. 방문가치 채널과 섞으면 "이미 거래처라 없었음"이 "추천이 나쁘다"로
   오염돼, 모델이 최고의 개척 후보(거래처와 닮은 집)를 피하도록 학습하게 된다.

③ 노출 로그: 피드백이 없어도 "무엇이 노출됐는지"가 있어야 배지별 lift(피드백
   그룹 비율 vs 노출 전체 비율)를 계산할 수 있다 — 피드백만 쌓으면 대조군이 없다.

전부 JSON Lines append-only 파일(+ 노출은 날짜·구역·스코어러 단위 스냅샷 파일)이다.
표본 규모(개인 사용자의 클릭)에서는 이 정도로 충분하고, 프로세스 재시작을 넘어
유지된다. data/ 전체가 gitignore돼 있어 개인정보가 커밋되지 않는다.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core import config
from scorers import base as scorer_base
from signals import base as signal_base

FEEDBACK_DIR = config.CACHE_DIR / "feedback"
FEEDBACK_EVENTS_PATH = FEEDBACK_DIR / "feedback_events.jsonl"
ATTRIBUTE_EVENTS_PATH = FEEDBACK_DIR / "attribute_events.jsonl"
EXPOSURE_DIR = FEEDBACK_DIR / "exposures"

LABEL_UP = "up"      # 방문가치 높았음
LABEL_DOWN = "down"  # 방문가치 없었음
ATTR_CLOSED = "폐업"
ATTR_CLIENT = "거래처"


def _now(now: datetime | None) -> datetime:
    return now or datetime.now()


def _to_jsonable(value):
    """numpy 스칼라·NaN·Timestamp 등 json.dumps가 못 삼키는 값을 안전하게 변환."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return None if np.isnan(v) else v
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_to_jsonable(record), ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def signal_snapshot(signal_results: dict[str, pd.DataFrame], est_id: str) -> dict:
    """업소 1곳의 신호값 벡터 스냅샷 — {신호id: {값, 원시값, 배지}}.

    signal_results는 ranking.py가 이미 계산해 둔 결과(신호id → DataFrame)라
    추가 계산 비용이 없다. 인덱싱은 매번 새로 하므로 업소 여러 곳을 스냅샷할
    때는 호출부에서 signal_results를 EST_ID로 미리 set_index해 재사용할 것.
    """
    snapshot = {}
    for sig_id, df in signal_results.items():
        indexed = df.set_index(signal_base.EST_ID) if df.index.name != signal_base.EST_ID else df
        if est_id not in indexed.index:
            continue
        row = indexed.loc[est_id]
        snapshot[sig_id] = {
            "값": row[signal_base.VALUE],
            "원시값": row[signal_base.RAW],
            "배지": row[signal_base.BADGE],
        }
    return snapshot


def log_exposure(
    scorer_id: str, cx: float, cy: float, radius: int,
    ranked: list[dict], now: datetime | None = None,
) -> None:
    """상위 N곳 노출 스냅샷 — 피드백 없는 업소도 lift 분석의 대조군이 되려면 필요하다.

    같은 (날짜, 구역, 스코어러) 조합은 파일을 덮어쓴다 — 하루 안의 재조회는 최신
    스냅샷 하나로 충분하고, rerun마다 쌓이는 것을 막는다.
    ranked: [{순위, 업소ID, 상호, 점수, 신호값, 배지}, ...]
    """
    ts = _now(now)
    key = f"{ts:%Y-%m-%d}|{scorer_id}|{round(cx, 6)}|{round(cy, 6)}|{radius}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    path = EXPOSURE_DIR / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "기준시각": ts.isoformat(),
        "스코어러": scorer_id,
        "중심": {"cx": cx, "cy": cy}, "반경": radius,
        "업소목록": ranked,
    }
    path.write_text(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=1), encoding="utf-8")


def record_feedback(
    est_id: str, name: str, label: str, scorer_id: str,
    cx: float, cy: float, radius: int, score: float,
    badges: list[str], signal_values: dict, now: datetime | None = None,
) -> None:
    """방문가치 피드백 1건 — 그 순간의 스냅샷을 통째로 남긴다 (신호값은 흘러가는 값)."""
    if label not in (LABEL_UP, LABEL_DOWN):
        raise ValueError(f"알 수 없는 라벨: {label}")
    record = {
        "시각": _now(now).isoformat(),
        "업소ID": est_id,
        "상호": name,
        "라벨": label,
        "스코어러": scorer_id,
        "중심": {"cx": cx, "cy": cy}, "반경": radius,
        "점수": score,
        "배지": badges,
        "신호값": signal_values,
    }
    _append_jsonl(FEEDBACK_EVENTS_PATH, record)


def record_attribute(est_id: str, name: str, attribute: str, value: bool, now: datetime | None = None) -> None:
    """업소 속성 토글 1건 (폐업했어요/우리 거래처예요) — 방문가치 피드백과 분리된 채널."""
    if attribute not in (ATTR_CLOSED, ATTR_CLIENT):
        raise ValueError(f"알 수 없는 속성: {attribute}")
    record = {
        "시각": _now(now).isoformat(),
        "업소ID": est_id,
        "상호": name,
        "속성": attribute,
        "값": value,
    }
    _append_jsonl(ATTRIBUTE_EVENTS_PATH, record)


def latest_feedback() -> dict[str, dict]:
    """업소ID → 가장 최근 피드백 {라벨, 시각}. 같은 업소를 다시 누르면 마지막 것이 이긴다."""
    latest: dict[str, dict] = {}
    for rec in _read_jsonl(FEEDBACK_EVENTS_PATH):
        latest[rec["업소ID"]] = {"라벨": rec["라벨"], "시각": rec["시각"]}
    return latest


def latest_attributes() -> dict[str, dict[str, bool]]:
    """업소ID → {속성: 최종값}. 속성별로 가장 최근 토글이 이긴다."""
    latest: dict[str, dict[str, bool]] = {}
    for rec in _read_jsonl(ATTRIBUTE_EVENTS_PATH):
        latest.setdefault(rec["업소ID"], {})[rec["속성"]] = rec["값"]
    return latest

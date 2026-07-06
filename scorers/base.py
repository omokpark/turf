"""스코어러 계약 — 신호들을 조합해 방문 우선순위 랭킹을 만든다

판단 원칙의 코드화: 반환의 모든 행은 근거 배지를 가져야 한다. 배지 없는 점수는
계약 위반이다 — 점수가 '왜'인지 설명하지 못하는 랭킹은 판단 문구와 다를 바 없기 때문.
부분 데이터 내성: signal_results에 없는 신호는 없는 대로 동작해야 한다.
"""

from typing import Protocol, runtime_checkable

import pandas as pd

from signals.base import AreaContext

# ── Scorer.score 반환 DataFrame의 컬럼 계약 ─────────────────────────────────
EST_ID = "업소ID"
SCORE = "점수"          # float: 높을수록 방문 우선
RANK = "순위"           # int: 1부터
BADGES = "근거배지목록"  # list[str]: 관측 사실 배지들 — 빈 리스트 금지

SCORE_COLUMNS = [EST_ID, SCORE, RANK, BADGES]


@runtime_checkable
class Scorer(Protocol):
    id: str            # "weighted_sum"
    label: str         # "가중합 베이스라인"
    description: str   # UI 설명문 — 어떤 신호를 어떻게 합치는지

    def score(self, signal_results: dict[str, pd.DataFrame], ctx: AreaContext) -> pd.DataFrame:
        """SCORE_COLUMNS 스키마의 DataFrame을 순위 오름차순으로 반환한다."""
        ...


def validate_score_result(df: pd.DataFrame) -> None:
    missing = set(SCORE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Scorer 출력 스키마 위반 — 누락 컬럼: {sorted(missing)}")
    if len(df) == 0:
        return
    no_badge = df[df[BADGES].map(len) == 0]
    if len(no_badge) > 0:
        raise ValueError(
            f"배지 없는 점수 {len(no_badge)}행 — 모든 점수는 근거 배지와 함께여야 합니다 (판단 원칙)."
        )


_SCORERS: dict[str, Scorer] = {}


def register_scorer(cls):
    instance = cls() if isinstance(cls, type) else cls
    if instance.id in _SCORERS:
        raise ValueError(f"Scorer id 중복: {instance.id}")
    _SCORERS[instance.id] = instance
    return cls


def available_scorers() -> list[Scorer]:
    return list(_SCORERS.values())


def clear() -> None:
    """테스트 전용."""
    _SCORERS.clear()

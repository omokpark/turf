"""프랜차이즈 판별(M4) — 상호명 출현 빈도로 체인점을 걸러 독립 업소만 남긴다.

프랜차이즈는 본사가 영업방침을 일괄 결정하므로 개별 방문 효율이 낮다는 판단 하에,
같은 정규화 상호가 여러 번 나오면 체인으로 간주해 신호값을 낮춘다(독립 업소=1, 체인=0
인 필터형 신호).

⚠️ 원 계획(REDESIGN_PLAN.md)은 "전국 1회 스캔" 기준 출현 빈도를 상정했으나, 아직
전국 스캔 데이터가 없다(Phase 5 예정 — 자치단체별로만 수집됨). 그래서 지금은
`ctx.reference`(수집된 범위, 현재는 자치단체 단위)를 기준으로 계산하고 배지에 그
범위를 명시한다 — 관측 사실만 말한다는 원칙상 "전국 기준"이라고 과장하지 않는다.

상호명 정규화는 matching/normalize.py(Phase 4 예정) 도입 전 임시 근사치다: 괄호 안
내용과 흔한 지점명 접미사(역/점/지점 등)를 제거하는 정도로, 완전한 지점명 분리는
아니다.
"""

import re

import pandas as pd

from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.registry import register_signal

CHAIN_THRESHOLD = 3  # 정규화 상호가 이 횟수 이상 출현하면 체인으로 간주

_PAREN_RE = re.compile(r"[\(（].*?[\)）]")
_BRANCH_SUFFIX_RE = re.compile(r"(역점|본점|직영점|지점|점)$")


def normalize_name(name: str) -> str:
    """상호명에서 지점명 흔적을 대략 제거한다 (완전한 정규화는 아님, 임시 근사치)."""
    n = _PAREN_RE.sub("", str(name)).strip()
    n = re.sub(r"\s+", "", n)
    n = _BRANCH_SUFFIX_RE.sub("", n)
    return n or str(name)


def _normalize_series(s: pd.Series) -> pd.Series:
    return s.fillna("").map(normalize_name)


@register_signal
class Franchise:
    id = "franchise"
    label = "프랜차이즈 판별"
    badge_icon = "🏪"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        open_df = ctx.establishments[ctx.establishments[schema.IS_OPEN]].copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        reference = ctx.reference if ctx.reference is not None else ctx.establishments
        counts = _normalize_series(reference[schema.NAME]).value_counts()

        open_df["_정규화상호"] = _normalize_series(open_df[schema.NAME])
        open_df["_출현횟수"] = open_df["_정규화상호"].map(counts).fillna(1).astype(int)

        rows = []
        for _, row in open_df.iterrows():
            n = int(row["_출현횟수"])
            is_chain = n >= CHAIN_THRESHOLD
            value = 0.0 if is_chain else 1.0
            # 배지는 체인일 때만 — "독립 추정"을 모든 업소에 붙이면 노이즈다. 요즘은 대부분이
            # 프랜차이즈라 체인이 방문 대상에서 빠질 이유도 없으므로(사용자 피드백 2026-07-06),
            # 점수 반영은 scorer 가중치 0으로 껐고 이 신호는 정보 배지로만 쓴다.
            badge = (
                f"{self.badge_icon} 체인 추정 — 수집 범위 내 '{row['_정규화상호']}' {n}회 출현"
                if is_chain
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: value,
                    RAW: n,
                    BADGE: badge,
                    DETAIL: "정규화 상호 출현 빈도는 현재 수집된 자치단체 범위 기준 (전국 스캔 전, Phase 5 예정)",
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

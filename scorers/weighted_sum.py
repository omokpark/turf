"""가중합 베이스라인 스코어러 — 가용 신호들의 값(0~1)을 가중 평균해 점수를 만든다.

부분 데이터 내성: signal_results에 없는 신호는 그 업소의 합산에서 빠지고 나머지
가중치로 재정규화된다. 배지는 각 신호가 준 배지문구를 그대로 모아 붙인다 — 어떤
업소든 배지가 하나도 없으면(모든 신호가 그 업소에 값이 없거나 배지가 None이면)
점수를 만들지 않는다(Scorer 계약: 배지 없는 점수 금지).
"""

import pandas as pd

from scorers import base as scorer_base
from scorers.base import register_scorer
from signals import base as signal_base

# 가중치 = 랭킹 정책 (신호 자체는 관측값만 계산, 어떻게 섞을지는 여기서 정한다):
# - recent_opening 1.5: 개업 직후(공급사 미확정)가 최우선이라는 영업 타이밍 축.
# - survivor 0.5: 생존 검증은 참고 등급 — 오래됐다고 상위를 독식하지 않도록 낮게.
# - liquor_adjacency 0.5: 단독 의미가 약한 부스터.
# - franchise 0.0: 점수 미반영, 체인 추정 배지만 정보로 표시 (요즘은 대부분 프랜차이즈라
#   제외가 과하다는 사용자 피드백 2026-07-06).
# - growth_momentum 0.5 / conversion_vector 0.5 (Phase 5): 골목·자리의 맥락 부스터 —
#   업소 자체의 신호(개업 타이밍·생존)보다 낮게.
# - night_index 0.5 (Phase 5, M7 v1): 야간 맥락 부스터. liquor_adjacency와 축이 겹치는
#   면이 있으나(주류친화 밀도) 심야 인구 축이 추가돼 별도 유지 — 둘 다 낮은 가중으로.
# - star_level 0.0: '알려진 스타'는 전용 스코어러(known_star)의 축 — 가중합의 신규 개업
#   우선 정책과 섞으면 큰 계정이 타이밍 랭킹을 밀어낸다. franchise처럼 배지만 표시.
DEFAULT_WEIGHTS = {
    "liquor_adjacency": 0.5,
    "recent_opening": 1.5,
    "survivor": 0.5,
    "franchise": 0.0,
    "growth_momentum": 0.5,
    "conversion_vector": 0.5,
    "night_index": 0.5,
    "star_level": 0.0,
}
FALLBACK_WEIGHT = 1.0


@register_scorer
class WeightedSum:
    id = "weighted_sum"
    label = "가중합 베이스라인"
    description = (
        "가용한 신호들의 값(0~1)을 가중 평균해 점수를 매깁니다. "
        "특정 업소에 없는 신호는 자동으로 빠지고 나머지 가중치로 재정규화됩니다."
    )

    def score(self, signal_results: dict[str, pd.DataFrame], ctx) -> pd.DataFrame:
        if not signal_results:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        merged: dict[str, dict] = {}
        for sig_id, df in signal_results.items():
            weight = DEFAULT_WEIGHTS.get(sig_id, FALLBACK_WEIGHT)
            for _, row in df.iterrows():
                eid = row[signal_base.EST_ID]
                entry = merged.setdefault(eid, {"weighted_sum": 0.0, "weight_total": 0.0, "badges": []})
                entry["weighted_sum"] += row[signal_base.VALUE] * weight
                entry["weight_total"] += weight
                badge = row[signal_base.BADGE]
                # None은 DataFrame을 거치며 NaN이 되기도 하는데 NaN은 truthy다 — pd.notna로 걸러야 한다
                if pd.notna(badge) and badge:
                    entry["badges"].append(badge)

        rows = []
        for eid, entry in merged.items():
            if entry["weight_total"] == 0 or not entry["badges"]:
                continue  # 근거 배지가 하나도 없으면 애초에 점수를 만들지 않는다
            rows.append(
                {
                    scorer_base.EST_ID: eid,
                    scorer_base.SCORE: round(entry["weighted_sum"] / entry["weight_total"], 4),
                    "_badges": entry["badges"],
                }
            )

        if not rows:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        out = pd.DataFrame(rows).sort_values(scorer_base.SCORE, ascending=False).reset_index(drop=True)
        out[scorer_base.RANK] = out.index + 1
        out[scorer_base.BADGES] = out["_badges"]
        return out[scorer_base.SCORE_COLUMNS]

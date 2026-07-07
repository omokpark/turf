"""프랜차이즈 판별(M4) — 상호명 출현 빈도로 체인점을 식별하는 정보 배지 신호.

점수에는 반영하지 않고(가중치 0 — 요즘은 대부분 프랜차이즈라 제외가 과하다는 사용자
피드백) 체인 추정 배지만 붙인다. VALUE는 독립=1/체인=0 필터형 값으로 유지해, 필요 시
다른 스코어러가 쓸 수 있게 둔다.

출현 빈도의 기준(우선순위):
1) **전국 스캔** (datasources/national_names — 전국 영업중 업소, Phase 5): 같은 정규화
   상호가 전국 NATIONAL_CHAIN_THRESHOLD곳 이상이면 체인. 전국 기준이라 동네 유일
   지점의 대형 체인(예: 써브웨이)도 잡는다. 흔한 상호의 우연 동명 오카운트를 줄이기
   위해 임계는 로컬보다 높게 둔다.
2) 폴백 — 수집 범위(자치단체): 전국 스캔 파일이 없으면 ctx.reference 안 출현 빈도로
   계산하고 배지에 그 범위를 명시한다 — 관측 사실만 말한다는 원칙상 과장하지 않는다.

상호명 정규화는 matching/normalize.py (단일 출처).
"""

import pandas as pd

from core import schema
from datasources.national_names import load_national_counts, scan_freshness
from matching.normalize import normalize_name
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.registry import register_signal

CHAIN_THRESHOLD = 3  # 폴백(수집 범위) 기준
NATIONAL_CHAIN_THRESHOLD = 5  # 전국 기준 — 우연 동명 오카운트 방어를 위해 더 높게


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

        national = load_national_counts()
        if national is not None:
            counts = national
            threshold = NATIONAL_CHAIN_THRESHOLD
            scope = "전국"
            detail = f"전국 영업중 업소 정규화 상호 출현 빈도 (스캔 {scan_freshness() or '기준일 미상'})"
        else:
            reference = ctx.reference if ctx.reference is not None else ctx.establishments
            counts = _normalize_series(reference[schema.NAME]).value_counts()
            threshold = CHAIN_THRESHOLD
            scope = "수집 범위"
            detail = "정규화 상호 출현 빈도는 현재 수집된 자치단체 범위 기준 (전국 스캔 파일 없음)"

        open_df["_정규화상호"] = _normalize_series(open_df[schema.NAME])
        open_df["_출현횟수"] = open_df["_정규화상호"].map(counts).fillna(1).astype(int)

        rows = []
        for _, row in open_df.iterrows():
            n = int(row["_출현횟수"])
            is_chain = n >= threshold
            value = 0.0 if is_chain else 1.0
            # 배지는 체인일 때만 — "독립 추정"을 모든 업소에 붙이면 노이즈다.
            badge = (
                f"{self.badge_icon} 체인 추정 — {scope} '{row['_정규화상호']}' {n:,}곳 영업 중"
                if is_chain
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: value,
                    RAW: n,
                    BADGE: badge,
                    DETAIL: detail,
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

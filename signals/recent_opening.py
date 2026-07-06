"""신규 개업 골든타임 — 개업 직후일수록 높은 신호.

주류 영업 관점에서 개업 직후는 공급사가 아직 결정되지 않았거나 굳지 않은 시기다
(REDESIGN_PLAN.md M8 버즈 모멘텀의 전제 — "개업 직후 = 주류 공급사 결정 시점이라
타이밍 가치 최대"). 생존자 지수(M2)가 오래 버틴 집만 상위로 밀어올리는 것을
균형 잡는 반대축: 인허가일자로부터 경과일이 짧을수록 1에 가깝고, GOLDEN_WINDOW_DAYS
를 지나면 0이 된다.

창 밖의 업소도 값 0·배지 None 행을 반환한다 — weighted_sum이 업소별 가용 가중치로
재정규화하기 때문에, 행을 아예 빼면 오래된 업소가 이 신호의 0점을 안 받아
균형 효과가 사라진다.
"""

import pandas as pd

from core import schema
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.registry import register_signal

GOLDEN_WINDOW_DAYS = 180  # 이 기간이 지나면 신호 0 — '개업 직후'로 보는 상한


@register_signal
class RecentOpening:
    id = "recent_opening"
    label = "신규 개업"
    badge_icon = "🆕"
    requires = frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]].dropna(subset=[schema.LICENSED_AT]).copy()
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        open_df["_경과일"] = (ctx.now - open_df[schema.LICENSED_AT]).dt.days
        rows = []
        for _, row in open_df.iterrows():
            days = int(row["_경과일"])
            value = max(0.0, 1.0 - days / GOLDEN_WINDOW_DAYS)
            badge = (
                f"{self.badge_icon} 개업 {days}일차 (인허가 {row[schema.LICENSED_AT]:%Y-%m-%d})"
                if value > 0
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(value, 4),
                    RAW: days,
                    BADGE: badge,
                    DETAIL: f"인허가일자 기준 경과일. {GOLDEN_WINDOW_DAYS}일까지 선형 감쇠",
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

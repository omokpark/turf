"""알려진 스타 스코어러 — 현재 게재 속도가 수집 반경 상위인 업소의 규모 랭킹.

목적지 지수(입지 대비 초과 = 숨겨진 스타)·가중합(방문 타이밍)과 다른 제3의 축:
"지금 언급량이 큰 계정" 그 자체. 스타 판정(속도 상위 20%, signals/star_level의
배지 부여 기준)을 통과한 업소만 랭킹한다 — 배지 없는 점수 금지 계약과도 일치.
증감(급증·급감)은 배지에 병기된 변곡 정보로, 순위에는 영향을 주지 않는다.
"""

import pandas as pd

from scorers import base as scorer_base
from scorers.base import register_scorer
from signals import base as signal_base


@register_scorer
class KnownStar:
    id = "known_star"
    label = "알려진 스타"
    description = (
        "현재 블로그 게재 속도(월 환산)가 수집 반경 내 상위인 업소. 업력으로 나누지 않아 "
        "'지금 언급량이 큰 계정'이 그대로 위로 옵니다. 직전 90일 대비 증감을 배지에 병기 "
        "(API 캡으로 직전 창이 잘리는 초상위 업소는 증감 생략). 게재 속도 상위 20% 밖은 제외."
    )

    def score(self, signal_results: dict[str, pd.DataFrame], ctx) -> pd.DataFrame:
        star = signal_results.get("star_level")
        if star is None or len(star) == 0:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        badged = star[star[signal_base.BADGE].notna()].copy()
        if len(badged) == 0:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        # 점수 = 게재 속도의 구역 내 백분위(신호 VALUE), 동점은 원시 속도(건/월)로 정렬
        badged = badged.sort_values(
            [signal_base.VALUE, signal_base.RAW], ascending=False
        ).reset_index(drop=True)
        out = pd.DataFrame(
            {
                scorer_base.EST_ID: badged[signal_base.EST_ID],
                scorer_base.SCORE: badged[signal_base.VALUE].round(4),
                scorer_base.RANK: badged.index + 1,
                scorer_base.BADGES: badged[signal_base.BADGE].map(lambda b: [b]),
            }
        )
        return out[scorer_base.SCORE_COLUMNS]

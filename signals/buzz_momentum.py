"""버즈 모멘텀(M8) — 최근 개업 업소 중 블로그 포스팅이 붙기 시작한 집.

개업 직후는 주류 공급사 결정 시점이라 타이밍 가치가 최대인데, 그중에서도 벌써
입소문(블로그)이 붙는 집은 우선 방문 대상이라는 신호. 쿼터 방어를 위해
**골든타임(개업 180일 이내) 업소만** Naver를 조회한다 — 다른 업소는 행 자체가 없다.
"""

import math

import pandas as pd

from core import schema
from datasources import naver
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.recent_opening import GOLDEN_WINDOW_DAYS
from signals.registry import register_signal

SATURATION_POSTS = 20  # 개업 직후 이 건수면 만점 — log 스케일


@register_signal
class BuzzMomentum:
    id = "buzz_momentum"
    label = "버즈 모멘텀"
    badge_icon = "🔥"
    requires = frozenset({"moi", "naver"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        cutoff = ctx.now - pd.Timedelta(days=GOLDEN_WINDOW_DAYS)
        golden = df[df[schema.IS_OPEN] & (df[schema.LICENSED_AT] >= cutoff)].dropna(subset=[schema.LICENSED_AT])
        if len(golden) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        rows = []
        for _, row in golden.iterrows():
            token = naver.address_token(row[schema.ADDR_ROAD], row[schema.ADDR_JIBUN])
            posts, latest = naver.blog_posts_since(row[schema.NAME], token, since=row[schema.LICENSED_AT])
            value = min(1.0, math.log1p(posts) / math.log1p(SATURATION_POSTS))
            days = int((ctx.now - row[schema.LICENSED_AT]).days)
            badge = (
                f"{self.badge_icon} 개업 {days}일차에 블로그 {posts}건 (최근 {latest:%m-%d})"
                if posts > 0
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: round(value, 4),
                    RAW: posts,
                    BADGE: badge,
                    DETAIL: f"'{row[schema.NAME]} {token}' 검색, 인허가일({row[schema.LICENSED_AT]:%Y-%m-%d}) 이후 포스팅 수",
                }
            )
        return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)

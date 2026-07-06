"""리뷰 모멘텀 — M1 목적지 지수의 분자 R (Naver판: 최근 6개월 블로그 수 기준)

R = log(1+최근 6개월 블로그 포스팅 수) / 업력년. 오래된 집에 쌓인 절대량이 아니라
"지금 입소문이 붙는 속도"를 재기 위해 업력으로 나눈다 (업력 하한 0.25년 — 갓 연 집의
분모 폭주 방지). VALUE는 반경 내 영업 업소 중 R의 백분위(0~1), RAW는 R 원값.

반경 내 영업 업소 전수를 조회하므로 M8보다 호출량이 크다 — 7일 파일 캐시(datasources/
naver.py)가 쿼터를 방어하고, 도보 상권 반경(≤400m)이 조회 범위를 자연히 제한한다.
"""

import math

import pandas as pd

from core import schema
from datasources import naver
from signals.base import AreaContext, BADGE, DETAIL, EST_ID, RAW, SIGNAL_COLUMNS, VALUE
from signals.registry import register_signal

WINDOW_MONTHS = 6
MIN_AGE_YEARS = 0.25


@register_signal
class ReviewMomentum:
    id = "review_momentum"
    label = "리뷰 모멘텀"
    badge_icon = "📝"
    requires = frozenset({"moi", "naver"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        df = ctx.establishments
        open_df = df[df[schema.IS_OPEN]].dropna(subset=[schema.LICENSED_AT])
        if len(open_df) == 0:
            return pd.DataFrame(columns=SIGNAL_COLUMNS)

        since = ctx.now - pd.DateOffset(months=WINDOW_MONTHS)
        rows = []
        for _, row in open_df.iterrows():
            token = naver.address_token(row[schema.ADDR_ROAD], row[schema.ADDR_JIBUN])
            posts, _ = naver.blog_posts_since(row[schema.NAME], token, since=since)
            age_years = max((ctx.now - row[schema.LICENSED_AT]).days / 365.25, MIN_AGE_YEARS)
            r = math.log1p(posts) / age_years
            badge = (
                f"{self.badge_icon} 최근 {WINDOW_MONTHS}개월 블로그 {posts}건 (업력 {age_years:.1f}년)"
                if posts > 0
                else None
            )
            rows.append(
                {
                    EST_ID: row[schema.SRC_ID],
                    VALUE: 0.0,  # 아래에서 백분위로 채움
                    RAW: round(r, 4),
                    BADGE: badge,
                    DETAIL: f"'{row[schema.NAME]} {token}' 검색, R = log(1+{posts})/{age_years:.1f}년",
                }
            )
        out = pd.DataFrame(rows, columns=SIGNAL_COLUMNS)
        if len(out) > 0:
            out[VALUE] = out[RAW].rank(pct=True).round(4)
        return out

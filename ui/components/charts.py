"""업종 구성 차트 컴포넌트"""

import altair as alt
import pandas as pd

from core import schema
from ui.state import NEUTRAL_COLOR


def category_bar_chart(by_category: pd.DataFrame, category_colors: dict) -> tuple[alt.Chart, int]:
    """업종별 개수·비율 가로 막대 차트. (차트, 전체 높이 px)를 돌려준다."""
    chart_df = by_category.copy().reset_index(drop=True)
    chart_df["순위"] = chart_df.index + 1
    chart_df["표시명"] = chart_df["순위"].astype(str) + "위 " + chart_df[schema.CAT_S]
    chart_df["라벨"] = chart_df["개수"].astype(str) + "곳 (" + chart_df["비율"].astype(str) + "%)"
    # 지도 범례와 같은 색상 매핑을 사용 — 필터로 선택하지 않은 업종은 중립색
    chart_df["색상"] = chart_df[schema.CAT_S].map(category_colors).fillna(NEUTRAL_COLOR)

    base = alt.Chart(chart_df).encode(
        y=alt.Y(
            "표시명:N",
            sort=alt.EncodingSortField(field="개수", order="descending"),
            title=None,
            axis=alt.Axis(labelLimit=240),
        )
    )
    bars = base.mark_bar().encode(
        x=alt.X("개수:Q", title="개수"),
        color=alt.Color("색상:N", scale=None, legend=None),
        tooltip=[
            alt.Tooltip(f"{schema.CAT_S}:N", title="업종"),
            alt.Tooltip("순위:Q", title="순위"),
            alt.Tooltip("개수:Q", title="개수"),
            alt.Tooltip("비율:Q", title="비율(%)"),
        ],
    )
    labels = base.mark_text(align="left", dx=3).encode(x="개수:Q", text="라벨:N")
    chart_height = max(320, 24 * len(chart_df))
    return (bars + labels).properties(height=chart_height), chart_height

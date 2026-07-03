"""업종별 집계·통계"""

import pandas as pd


def analyze(shops: list[dict], my_category: str | None = None) -> dict:
    """상가업소 리스트에서 음식점만 골라 업종 소분류 기준으로 집계한다."""
    df = pd.DataFrame(shops)
    food_df = df[df["상권업종대분류명"] == "음식"]
    total = len(food_df)

    by_category = (
        food_df.groupby("상권업종소분류명")
        .size()
        .reset_index(name="개수")
        .sort_values("개수", ascending=False)
        .reset_index(drop=True)
    )
    by_category["비율"] = (by_category["개수"] / total * 100).round(1)

    my_rank = None
    my_count = 0
    my_pct = 0.0
    if my_category:
        match = by_category[by_category["상권업종소분류명"] == my_category]
        if not match.empty:
            idx = match.index[0]
            my_rank = idx + 1
            my_count = int(match.loc[idx, "개수"])
            my_pct = float(match.loc[idx, "비율"])

    return {
        "total": total,
        "by_category": by_category,
        "my_rank": my_rank,
        "my_count": my_count,
        "my_pct": my_pct,
    }

"""업종별 집계·통계

입력은 ROSTER 스키마(core/schema.py)를 따르는 DataFrame 또는 그 dict 리스트다.
소스별 컬럼명(SEMAS 상권업종소분류명 등) → schema 상수 변환은 datasource 어댑터
(datasources/semas.py 등)의 책임이고, 여기는 schema 상수만 쓴다 (Phase 3 전환).
"""

import pandas as pd

from core import schema


def analyze(shops: pd.DataFrame | list[dict], my_category: str | None = None) -> dict:
    """명부에서 음식점만 골라 업종 소분류 기준으로 집계한다."""
    if isinstance(shops, pd.DataFrame):
        # columns를 명시해 빈 DataFrame이어도(반경 내 업소 0곳) KeyError 없이 빈 집계를 반환한다.
        df = shops.reindex(columns=schema.ROSTER_COLUMNS)
    else:
        df = pd.DataFrame(shops, columns=schema.ROSTER_COLUMNS)
    food_df = df[df[schema.CAT_L] == "음식"]
    total = len(food_df)

    by_category = (
        food_df.groupby(schema.CAT_S)
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
        match = by_category[by_category[schema.CAT_S] == my_category]
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
        "food_df": food_df,
    }

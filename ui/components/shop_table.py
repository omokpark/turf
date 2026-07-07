"""업소 목록 표 + CSV 다운로드 컴포넌트"""

import pandas as pd
import streamlit as st

from core import schema

# 셀 값이 이 문자로 시작하면 Excel/Sheets가 수식으로 해석할 수 있다(CSV 인젝션).
# 상호명·주소는 외부 데이터라 통제할 수 없으므로, 다운로드 시 앞에 작은따옴표를 붙여
# 항상 텍스트로 취급되게 한다 — 화면 표시(st.dataframe)는 원본 그대로 둔다.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _neutralize_formulas(df: pd.DataFrame) -> pd.DataFrame:
    def guard(value):
        text = str(value)
        return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else value

    return df.map(guard)


def render_shop_table(food_df: pd.DataFrame, selected_categories: list[str]) -> None:
    table_df = food_df
    if selected_categories:
        table_df = table_df[table_df[schema.CAT_S].isin(selected_categories)]
    st.markdown("**📋 업소 목록**" + (" (선택 업종)" if selected_categories else " (전체)"))
    display_table = (
        table_df[[schema.NAME, schema.CAT_S, schema.ADDR_ROAD]]
        .rename(columns={schema.NAME: "상호명", schema.CAT_S: "업종", schema.ADDR_ROAD: "주소"})
        .reset_index(drop=True)
    )
    st.dataframe(
        display_table,
        use_container_width=True,
        column_config={
            "상호명": st.column_config.TextColumn(width="medium"),
            "업종": st.column_config.TextColumn(width="small"),
            "주소": st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button(
        "⬇️ 업소 목록 CSV 다운로드",
        _neutralize_formulas(display_table).to_csv(index=False).encode("utf-8-sig"),
        file_name="turf_업소목록.csv",
        mime="text/csv",
    )

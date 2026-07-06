"""업소 목록 표 + CSV 다운로드 컴포넌트"""

import pandas as pd
import streamlit as st

from core import schema


def render_shop_table(food_df: pd.DataFrame, selected_categories: list[str]) -> None:
    table_df = food_df
    if selected_categories:
        table_df = table_df[table_df[schema.CAT_S].isin(selected_categories)]
    st.markdown("**업소 목록**" + (" (선택 업종)" if selected_categories else " (전체)"))
    display_table = (
        table_df[[schema.NAME, schema.CAT_S, schema.ADDR_ROAD]]
        .rename(columns={schema.NAME: "상호명", schema.CAT_S: "업종", schema.ADDR_ROAD: "주소"})
        .reset_index(drop=True)
    )
    st.dataframe(display_table, use_container_width=True)
    st.download_button(
        "업소 목록 CSV 다운로드",
        display_table.to_csv(index=False).encode("utf-8-sig"),
        file_name="turf_업소목록.csv",
        mime="text/csv",
    )

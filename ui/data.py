"""UI 계층 공용 데이터 로더 — st.cache_data 래퍼의 단일 출처

같은 시그니처의 _load_roster가 app.py·outlook·ranking에 3벌 복제돼 있던 것을 통합.
st.cache_data는 함수 단위로 캐시를 가지므로 3벌이면 같은 명부가 메모리에 3번 올라간다.
"""

import pandas as pd
import streamlit as st

from datasources import moi_store


@st.cache_data(ttl=600, show_spinner=False)
def _roster_cached(cache_key: tuple) -> pd.DataFrame:
    return moi_store.load_roster()


def load_roster() -> pd.DataFrame:
    """수집된 인허가 명부 전체. 파티션 추가·재수집 시(cache_token 변화) 자동 무효화."""
    return _roster_cached(moi_store.cache_token())

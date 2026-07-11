"""CSV 내보내기 안전 유틸 — 수식 주입(CSV injection) 방지

셀 값이 =·+·-·@로 시작하면 Excel/Sheets가 수식으로 해석할 수 있다. 상호명·주소는
외부 데이터라 통제할 수 없으므로 다운로드 시 앞에 작은따옴표를 붙여 항상 텍스트로
취급되게 한다 (화면 표시는 원본 유지, 다운로드 데이터에만 적용).
"""

import pandas as pd

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralize_formulas(df: pd.DataFrame) -> pd.DataFrame:
    def guard(value):
        text = str(value)
        return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else value

    return df.map(guard)

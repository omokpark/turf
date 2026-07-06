"""M0 구역 아웃룩의 공용 계산 헬퍼

- 주류친화 업태 분류 (M5·M6과 공유하게 될 기준표)
- 국면 궤적: 개업 증감 × 폐업 증감 → 4사분면 라벨 (📈확장/🔄교체 활발/😴정체/📉수축)
- 격자 percentile: 구역 값의 상대화 — 같은 기준 명부(시군구)를 500m 격자로 잘라
  각 셀에서 같은 지표를 계산하고, 우리 구역 값이 그중 몇 백분위인지 구한다.

모든 출력은 관측 사실만 담는다 (판단 원칙).
"""

import math

import pandas as pd

from core import schema

# ── 주류친화 업태 분류 ────────────────────────────────────────────────────────
# 업태구분명이 직접 주류 중심임을 말하는 값들 (LOCALDATA 표준 업태 + 업종 파일명)
LIQUOR_CATS = {
    "호프/통닭",
    "정종/대포집/소주방",
    "감성주점",
    "간이주점",
    "라이브카페",
    "단란주점",
    "유흥주점",
}
# 업태가 '한식' 등으로 뭉뚱그려진 주점을 상호명으로 보정 (보수적 목록)
LIQUOR_NAME_KEYWORDS = ["호프", "주점", "포차", "술집", "비어", "맥주", "이자카야", "펍", "와인바"]


def is_liquor_friendly(cat_s: pd.Series, name: pd.Series) -> pd.Series:
    """행별 주류친화 여부. 업태 일치 또는 상호명 키워드 포함."""
    by_cat = cat_s.isin(LIQUOR_CATS)
    lowered = name.fillna("").str.lower()
    by_name = pd.Series(False, index=name.index)
    for kw in LIQUOR_NAME_KEYWORDS:
        by_name |= lowered.str.contains(kw.lower(), regex=False)
    return by_cat | by_name


# ── 주소 키 (trend.site_turnover와 동일 규칙 — 도로명 우선, 공백 정리) ─────────
def address_key(df: pd.DataFrame) -> pd.Series:
    road = df[schema.ADDR_ROAD].fillna("").astype(str)
    jibun = df[schema.ADDR_JIBUN].fillna("").astype(str)
    key = road.where(road.str.len() > 0, jibun)
    return key.str.replace(r"\s+", " ", regex=True).str.strip()


# ── 국면 궤적 ────────────────────────────────────────────────────────────────
PHASE_EXPANSION = "📈 확장"
PHASE_CHURN = "🔄 교체 활발"
PHASE_STAGNANT = "😴 정체"
PHASE_DECLINE = "📉 수축"


def _phase_label(d_open: int, d_close: int) -> str:
    open_up = d_open > 0
    close_up = d_close > 0
    if open_up and not close_up:
        return PHASE_EXPANSION
    if open_up and close_up:
        return PHASE_CHURN
    if not open_up and close_up:
        return PHASE_DECLINE
    return PHASE_STAGNANT


def phase_trajectory(df: pd.DataFrame, years: int = 5, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """연도별 (개업, 폐업, 전년 대비 증감, 국면) — 국면 매트릭스 차트의 데이터.

    반환: [연도, 개업, 폐업, 개업증감, 폐업증감, 국면]. 첫 해는 증감 기준이 없어 제외되며,
    올해는 진행 중(부분 연도)이므로 제외한다 — 연말까지 안 온 해를 전년과 비교하면
    항상 감소로 왜곡되기 때문.
    """
    today = today or pd.Timestamp.today()
    # 기준선(전년)이 필요하므로 1년 더 뒤에서 시작하고, 올해는 부분 연도라 뺀다
    start_year = today.year - years
    end_year = today.year - 1

    opened = df[schema.LICENSED_AT].dt.year
    closed = df[schema.CLOSED_AT].dropna().dt.year
    rows = []
    prev_open = prev_close = None
    for y in range(start_year, end_year + 1):
        n_open = int((opened == y).sum())
        n_close = int((closed == y).sum())
        if prev_open is not None:
            d_open, d_close = n_open - prev_open, n_close - prev_close
            rows.append(
                {
                    "연도": y,
                    "개업": n_open,
                    "폐업": n_close,
                    "개업증감": d_open,
                    "폐업증감": d_close,
                    "국면": _phase_label(d_open, d_close),
                }
            )
        prev_open, prev_close = n_open, n_close
    return pd.DataFrame(rows)


# ── 격자 percentile ──────────────────────────────────────────────────────────
GRID_M = 500
MIN_CELL_ROWS = 30
MIN_CELLS = 8


def grid_percentile(
    reference: pd.DataFrame,
    value_fn,
    focal_value: float,
    grid_m: int = GRID_M,
    min_cell_rows: int = MIN_CELL_ROWS,
    min_cells: int = MIN_CELLS,
) -> float | None:
    """기준 명부를 격자로 잘라 셀마다 value_fn(cell_df)을 계산하고,
    focal_value의 백분위(0~100)를 돌려준다. 셀이 부족하면 None (percentile 생략).

    value_fn은 표본 부족 등으로 None을 반환할 수 있다 — 그 셀은 제외.
    """
    coords = reference.dropna(subset=[schema.LAT, schema.LON])
    if len(coords) == 0 or focal_value is None:
        return None
    lat_step = grid_m / 111_320
    mid_lat = coords[schema.LAT].median()
    lon_step = grid_m / (111_320 * math.cos(math.radians(mid_lat)))
    cell = (
        (coords[schema.LAT] / lat_step).round().astype(int).astype(str)
        + "_"
        + (coords[schema.LON] / lon_step).round().astype(int).astype(str)
    )
    values = []
    for _, cell_df in coords.groupby(cell):
        if len(cell_df) < min_cell_rows:
            continue
        v = value_fn(cell_df)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            values.append(v)
    if len(values) < min_cells:
        return None
    values_s = pd.Series(values)
    return round(float((values_s <= focal_value).mean() * 100), 1)

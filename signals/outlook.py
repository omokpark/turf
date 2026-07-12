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


# 주류 판매가 법적으로 불가한 인허가 업종 (업종대 = 인허가 서비스 구분)
NO_LIQUOR_CAT_L = "휴게음식점"


def is_liquor_friendly(cat_s: pd.Series, name: pd.Series, cat_l: pd.Series | None = None) -> pd.Series:
    """행별 주류친화 여부. 업태 일치 또는 상호명 키워드 포함.

    cat_l(업종대)을 주면 휴게음식점(주류 판매 불가 인허가)은 상호에 '펍'이 붙어 있어도
    제외한다 — 휴게음식점 수집(2026-07-12) 이후 분모 오염 방지.
    """
    by_cat = cat_s.isin(LIQUOR_CATS)
    lowered = name.fillna("").str.lower()
    by_name = pd.Series(False, index=name.index)
    for kw in LIQUOR_NAME_KEYWORDS:
        by_name |= lowered.str.contains(kw.lower(), regex=False)
    result = by_cat | by_name
    if cat_l is not None:
        result &= cat_l.fillna("") != NO_LIQUOR_CAT_L
    return result


# ── 주류친화도 점수 (M6 업종 전환 벡터용, 0~3) ──────────────────────────────────
# 3=주류가 본업(유흥·단란), 2=주류 중심 일반음식(호프·주점류), 1=식사+반주 가능, 0=주류 무관
AFFINITY_3 = {"유흥주점", "단란주점"}
AFFINITY_2 = {"호프/통닭", "정종/대포집/소주방", "감성주점", "간이주점", "라이브카페"}
AFFINITY_0 = {"카페", "까페", "커피숍", "다방", "전통찻집", "키즈카페", "분식", "김밥(도시락)", "제과점영업", "패스트푸드", "아이스크림"}


def liquor_affinity(cat_s: str, name: str, cat_l: str | None = None) -> int:
    """업태·상호로 추정한 주류친화도 0~3. 모호하면 1(식사+반주 가능한 일반음식) 취급.

    cat_l(업종대)이 휴게음식점이면 무조건 0 — 주류 판매가 법적으로 불가한 인허가라
    업태가 '기타'든 상호가 '펍'이든 방문 영업 대상이 아니다.
    """
    if cat_l == NO_LIQUOR_CAT_L:
        return 0
    cat = (cat_s or "").strip()
    if cat in AFFINITY_3:
        return 3
    if cat in AFFINITY_2:
        return 2
    lowered = (name or "").lower()
    if any(kw.lower() in lowered for kw in LIQUOR_NAME_KEYWORDS):
        return 2
    if cat in AFFINITY_0:
        return 0
    return 1


# ── 주소 키 (자리 식별용 — 도로명 우선, 공백·주석 정리) ────────────────────────
def address_key(df: pd.DataFrame) -> pd.Series:
    """자리(호실 수준) 식별 키.

    Phase 5 강화: 말미의 법정동 주석 괄호("... 강남대로 390, 2층 (역삼동)")와 쉼표 주변
    공백 표기 차이를 제거한다 — 같은 자리가 등록 시기에 따라 주석 유무만 다른 경우를
    같은 키로 묶는다. 건물 전체를 하나로 뭉개지는 않는다(층·호 정보는 유지) — 한 건물에
    여러 업소가 정상 공존하므로 건물 단위 병합은 자리회전을 과대 계산한다.
    """
    road = df[schema.ADDR_ROAD].fillna("").astype(str)
    jibun = df[schema.ADDR_JIBUN].fillna("").astype(str)
    key = road.where(road.str.len() > 0, jibun)
    key = key.str.replace(r"\s*\([^()]*\)\s*$", "", regex=True)  # 말미 (법정동) 주석 제거
    key = key.str.replace(r"\s*,\s*", ",", regex=True)  # 쉼표 주변 공백 통일
    return key.str.replace(r"\s+", " ", regex=True).str.strip()


# ── 국면 궤적 ────────────────────────────────────────────────────────────────
PHASE_EXPANSION = "📈 확장"
PHASE_CHURN = "🔄 교체 활발"
PHASE_STAGNANT = "😴 정체"
PHASE_DECLINE = "📉 수축"

# 증감 완충대: 직전 기간 대비 ±10% 안쪽 변화는 노이즈로 보고 '변화 없음' 취급.
# 부호만 보면 개업 12→13(+8%)도 '확장'이 되는 과민 판정을 막는다 (2026-07-12).
PHASE_BUFFER = 0.10


def _increased(cur: int, prev: int) -> bool:
    """직전 대비 유의미한 증가인가 — 완충대(±10%)를 넘어야 증가로 친다."""
    return cur > prev * (1 + PHASE_BUFFER)


def _phase_label(cur_open: int, prev_open: int, cur_close: int, prev_close: int) -> str:
    open_up = _increased(cur_open, prev_open)
    close_up = _increased(cur_close, prev_close)
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
            rows.append(
                {
                    "연도": y,
                    "개업": n_open,
                    "폐업": n_close,
                    "개업증감": n_open - prev_open,
                    "폐업증감": n_close - prev_close,
                    "국면": _phase_label(n_open, prev_open, n_close, prev_close),
                }
            )
        prev_open, prev_close = n_open, n_close
    return pd.DataFrame(rows)


def current_phase(df: pd.DataFrame, today: pd.Timestamp | None = None) -> dict | None:
    """'지금' 국면 — 최근 12개월 vs 직전 12개월 이동창.

    phase_trajectory는 달력 연도 기준이라 올해(부분 연도)를 제외하면 7월에 '작년 기준'
    국면이 나온다 — 최대 18개월 지연. 헤드라인 국면은 이 이동창 판정을 쓴다 (2026-07-12).
    반환: {국면, 최근개업, 최근폐업, 직전개업, 직전폐업} — 표본이 전혀 없으면 None.
    """
    today = today or pd.Timestamp.today()
    mid = today - pd.DateOffset(months=12)
    start = today - pd.DateOffset(months=24)
    opened = df[schema.LICENSED_AT]
    closed = df[schema.CLOSED_AT]
    cur_open = int(opened.between(mid, today).sum())
    prev_open = int(opened.between(start, mid).sum())
    cur_close = int(closed.between(mid, today).sum())
    prev_close = int(closed.between(start, mid).sum())
    if cur_open + prev_open + cur_close + prev_close == 0:
        return None
    return {
        "국면": _phase_label(cur_open, prev_open, cur_close, prev_close),
        "최근개업": cur_open,
        "최근폐업": cur_close,
        "직전개업": prev_open,
        "직전폐업": prev_close,
    }


# ── 격자 percentile ──────────────────────────────────────────────────────────
GRID_M = 500
MIN_CELL_ROWS = 30
MIN_CELLS = 8


def grid_cell_ids(df: pd.DataFrame, grid_m: int = GRID_M) -> pd.Series:
    """행별 격자 셀 ID ("위도인덱스_경도인덱스"). 좌표 결측 행은 호출 전에 걸러야 한다."""
    lat_step = grid_m / 111_320
    mid_lat = df[schema.LAT].median()
    lon_step = grid_m / (111_320 * math.cos(math.radians(mid_lat)))
    return (
        (df[schema.LAT] / lat_step).round().astype(int).astype(str)
        + "_"
        + (df[schema.LON] / lon_step).round().astype(int).astype(str)
    )


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
    cell = grid_cell_ids(coords, grid_m)
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

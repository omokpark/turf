"""화면별 챗봇 컨텍스트 빌더 — 지금 화면에 표시된 데이터를 마크다운 텍스트로 직렬화한다.

순수 함수만 둔다(API 호출·Streamlit 의존 없음 → 유닛 테스트 가능). 챗봇은 여기서
만든 문자열만 근거로 답한다 — 새 검색·추정 금지(CLAUDE.md 판단 원칙). 행 상한을
넘기면 "총 N곳 중 상위 M곳만 포함"을 반드시 명시한다(조용한 절단 금지).
"""

from __future__ import annotations

import pandas as pd

from core import schema
from signals import base as signal_base
from signals.outlook import current_phase
from signals.registry import available_indicators, get_signal
from timeline import trend

# 지표 모듈 import = 레지스트리 등록 → available_indicators()의 id→label 매핑에 필요
# (호출부가 어디든 outlook_context가 지표 이름을 채울 수 있도록 여기서도 등록한다).
import signals.cohort_survival  # noqa: F401
import signals.liquor_shift  # noqa: F401
import signals.net_momentum  # noqa: F401

PYEONG_PER_M2 = 1 / 3.3058  # 1평 = 3.3058㎡
MAP_MAX_ROWS = 400
RANKING_MAX_ROWS = 500  # 방문 우선순위는 원칙상 '근거 있는 전체'를 담되, 과대 반경 안전판
RECENT_MAX_ROWS = 40
RECENT_OPEN_DAYS = 90     # 지도·구역동향의 '신규' 정의와 동일
RECENT_CLOSE_DAYS = 180   # '폐업' 정의와 동일 (신고 지연 감안)


def _pyeong(area_m2) -> str:
    if area_m2 is None or pd.isna(area_m2) or area_m2 <= 0:
        return "-"
    return f"{float(area_m2):.0f}㎡({float(area_m2) * PYEONG_PER_M2:.0f}평)"


def _cell(v) -> str:
    """표 셀 안전화 — None/NaN은 '-', 파이프는 이스케이프(마크다운 표 깨짐 방지)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return str(v).replace("|", "\\|").replace("\n", " ").strip() or "-"


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "(해당 없음)"
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(_cell(c) for c in r) + " |" for r in rows)
    return f"{head}\n{sep}\n{body}"


# ── 🗺️ 지도 ────────────────────────────────────────────────────────────────
def map_context(display: pd.DataFrame | None, cx: float, cy: float, radius: int, only_core: bool) -> str:
    scope = "주류 중심 업태(호프·주점급)만" if only_core else "주류 판매 가능 업소 전체"
    if display is None or len(display) == 0:
        return (
            f"# 화면: 🗺️ 지도\n반경 {radius}m · {scope}\n\n"
            "이 지역은 인허가 데이터가 수집되지 않아 표시할 업소가 없습니다."
        )

    n_close = int((display["상태"] == "폐업").sum())
    n_new = int((display["상태"] == "신규").sum())
    n_active = int((display["상태"] != "폐업").sum())

    shown = display.head(MAP_MAX_ROWS)
    trunc = ""
    if len(display) > MAP_MAX_ROWS:
        trunc = f"\n\n⚠️ 총 {len(display):,}곳 중 상위 {MAP_MAX_ROWS}곳만 아래 표에 포함(나머지는 화면 지도에만 표시)."

    rows = [
        [
            r[schema.NAME], r[schema.CAT_S], r["상태"],
            _pyeong(r.get(schema.AREA_M2)), r.get(schema.ADDR_ROAD),
        ]
        for _, r in shown.iterrows()
    ]
    table = _table(["상호", "업태", "상태", "면적", "도로명주소"], rows)
    return (
        f"# 화면: 🗺️ 지도\n"
        f"반경 {radius}m · {scope}\n"
        f"요약: 주류 가능 {n_active:,}곳 · 🟢최근 {RECENT_OPEN_DAYS}일 신규 {n_new} · "
        f"🔴최근 {RECENT_CLOSE_DAYS}일 폐업 {n_close}\n"
        f"'상태'는 신규(최근 {RECENT_OPEN_DAYS}일 개업)/영업/폐업(최근 {RECENT_CLOSE_DAYS}일). "
        f"면적은 인허가 소재지면적(㎡)과 평 환산.\n\n"
        f"## 업소 목록\n{table}{trunc}"
    )


def _signal_label(sig_id: str) -> str:
    try:
        return get_signal(sig_id).label
    except KeyError:
        return sig_id


def _signal_detail_text(est_id: str, indexed_signals: dict[str, pd.DataFrame]) -> str:
    """업소 1곳의 신호별 '상세' 설명(배지 문구보다 상세) — "라벨: 상세" 조각을 모은다."""
    parts = []
    for sig_id, df in indexed_signals.items():
        if est_id not in df.index:
            continue
        detail = df.loc[est_id, signal_base.DETAIL]
        if pd.notna(detail) and detail:
            parts.append(f"{_signal_label(sig_id)}: {detail}")
    return " / ".join(parts) if parts else "-"


# ── 🎯 방문 우선순위 ──────────────────────────────────────────────────────────
def ranking_context(
    top: pd.DataFrame,
    rest: pd.DataFrame,
    scorer,
    now_phase: dict | None,
    n_excluded: int,
    radius: int,
    indexed_signals: dict[str, pd.DataFrame],
) -> str:
    """top(화면에 카드로 보이는 상위 30곳, Google 교차검증 포함)과 rest(31위 이하 —
    근거는 있으나 카드로는 안 보이는 나머지)를 모두 컨텍스트에 담는다. '화면에 없는
    정보'는 배지·신호 자체가 없는 것만 뜻하고, 31위 이하는 화면 밖이라도 답변 가능."""
    phase = f"현재 국면: {now_phase['국면']}\n" if now_phase else ""
    excluded = f"주류 판매 불가 업소 {n_excluded}곳은 랭킹에서 제외됨.\n" if n_excluded else ""

    combined = pd.concat([top, rest], ignore_index=True) if len(rest) else top
    total = len(combined)
    shown = combined.head(RANKING_MAX_ROWS)
    trunc = ""
    if total > RANKING_MAX_ROWS:
        trunc = f"\n\n⚠️ 총 {total:,}곳 중 상위 {RANKING_MAX_ROWS}곳만 아래 표에 포함."

    rows = []
    for _, r in shown.iterrows():
        badges = r.get("근거배지목록") or []
        rows.append([
            r.get("순위"), r[schema.NAME], r[schema.CAT_S],
            f"{float(r['점수']):.3f}" if pd.notna(r.get("점수")) else "-",
            r.get(schema.ADDR_ROAD),
            " / ".join(str(b) for b in badges) if isinstance(badges, (list, tuple)) else "-",
            _signal_detail_text(r["업소ID"], indexed_signals),
        ])
    table = _table(["순위", "상호", "업태", "점수", "도로명주소", "근거배지", "신호상세"], rows)
    return (
        f"# 화면: 🎯 방문 우선순위\n"
        f"랭킹 기준: {scorer.label} — {scorer.description}\n"
        f"반경 {radius}m · 근거 있는 전체 {total:,}곳 (이 중 상위 {len(top)}곳만 화면에 카드로 표시, "
        f"Google 교차검증도 상위 {len(top)}곳까지만 적용됨)\n{phase}{excluded}"
        f"배지·신호상세에는 관측 사실만 담김(블로그 관측 건수·시점, 기대치 대비 배수, 신규 개업 경과일, "
        f"구글 평점·리뷰수 등). 블로그 '글 원문'은 수집하지 않으므로 이 데이터에 없다.\n\n"
        f"## 방문 우선순위 목록 (화면 카드 밖의 순위도 포함)\n{table}{trunc}"
    )


# ── 📈 구역 동향 ───────────────────────────────────────────────────────────────
def outlook_context(
    local: pd.DataFrame,
    near: pd.DataFrame,
    results_by_id: dict,
    radius: int,
    eff_radius: int,
    widened: bool,
) -> str:
    labels = {ind.id: ind.label for ind in available_indicators({"moi"})}
    basis = (
        f"국면·지표 기준 반경 {eff_radius}m(표본이 얇아 담당구역으로 확대) · 최근 변화 리스트는 선택 반경 {radius}m"
        if widened
        else f"기준 반경 {eff_radius}m"
    )

    phase = current_phase(local)
    if phase:
        phase_md = (
            f"현재 국면: {phase['국면']} "
            f"(최근 12개월 개업 {phase['최근개업']}·폐업 {phase['최근폐업']} vs "
            f"직전 12개월 개업 {phase['직전개업']}·폐업 {phase['직전폐업']})"
        )
    else:
        phase_md = "현재 국면: 표본 없음"

    ind_lines = []
    for sid, res in results_by_id.items():
        label = labels.get(sid, sid)
        prev = f" · 직전 {res.previous:.2f}" if res.previous is not None else ""
        pct = f" · 구역 내 백분위 {res.percentile:.0f}%" if res.percentile is not None else ""
        ind_lines.append(f"- **{label}**: {res.fact} (현재값 {res.current:.2f}{prev}{pct})")
    ind_md = "\n".join(ind_lines) if ind_lines else "(지표 없음)"

    recent = trend.recent_openings(near, days=RECENT_OPEN_DAYS)
    closed = trend.recent_closings(near, days=RECENT_CLOSE_DAYS)

    def _recent_table(df: pd.DataFrame, elapsed_col: str) -> str:
        shown = df.sort_values(elapsed_col).head(RECENT_MAX_ROWS)
        rows = [[r[schema.NAME], r[schema.CAT_S], int(r[elapsed_col])] for _, r in shown.iterrows()]
        note = f"\n(총 {len(df)}곳 중 최근 {RECENT_MAX_ROWS}곳)" if len(df) > RECENT_MAX_ROWS else ""
        return _table(["상호", "업태", "경과일"], rows) + note

    new_md = _recent_table(recent, "개업경과일") if len(recent) else "(없음)"
    close_md = _recent_table(closed, "폐업경과일") if len(closed) else "(없음)"

    return (
        f"# 화면: 📈 구역 동향\n{basis}\n{phase_md}\n\n"
        f"## 핵심 지표 (값의 '좋다/나쁘다'가 아니라 구역 내 상대 위치)\n{ind_md}\n\n"
        f"## 최근 신규 개업 (선택 반경 {radius}m, 최근 {RECENT_OPEN_DAYS}일)\n{new_md}\n\n"
        f"## 최근 폐업 (선택 반경 {radius}m, 최근 {RECENT_CLOSE_DAYS}일)\n{close_md}"
    )

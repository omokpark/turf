"""전역 스타일 — 가독성·가로스크롤 방지를 위한 최소 CSS 1회 주입

여기 문자열은 전부 고정 상수다(외부 데이터 보간 없음) — unsafe_allow_html은
turf 코드베이스에서 유일하게 여기서만 쓰이고, 사용자·API 데이터가 섞이지 않으므로
XSS 위험이 없다. 배지·상호명처럼 외부 데이터를 HTML로 넣을 때는 반드시
ui/components/badges.py의 이스케이프 경로를 거칠 것.
"""

import streamlit as st

_CSS = """
<style>
/* ── 가로스크롤 방지: 어떤 위젯도 뷰포트 밖으로 넘치지 않게 ───────────────── */
img, iframe, video, .stAltairChart, .stPlotlyChart, .stDataFrame, .stTable,
.element-container, .stMarkdown, .stCaption, .stTextInput, .stButton {
    max-width: 100% !important;
}
pre, code { white-space: pre-wrap !important; word-break: break-word !important; }
.stMarkdown p, .stCaption, .stMarkdown li { overflow-wrap: anywhere; }

/* ── 가독성: 본문 줄간격·여백 ────────────────────────────────────────────── */
.stMarkdown p, .stMarkdown li { line-height: 1.55; }
div[data-testid="stMetricValue"] { font-size: 1.5rem; }
div[data-testid="stMetricLabel"] { font-size: 0.85rem; opacity: 0.85; }

/* ── 카드 컨테이너(랭킹 등)는 st.container(border=True)가 만드는 테두리를
   살짝 다듬어 카드처럼 보이게 ─────────────────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
}

/* ── 배지 칩 ──────────────────────────────────────────────────────────── */
.turf-badge-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 2px; }
.turf-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    background: rgba(120, 130, 140, 0.14);
    font-size: 0.82rem;
    line-height: 1.5;
    white-space: normal;
    word-break: break-word;
}
.turf-badge.turf-badge-warn { background: rgba(211, 84, 0, 0.16); }
.turf-badge.turf-badge-good { background: rgba(26, 127, 92, 0.14); }

/* ── 랭킹 카드 헤더 줄 ────────────────────────────────────────────────── */
.turf-rank-medal { font-size: 1.4rem; line-height: 1; }
.turf-rank-num { font-size: 1.1rem; font-weight: 700; opacity: 0.7; }

/* ── 플로팅 챗봇 (우하단 FAB + 고정 패널) ──────────────────────────────── */
/* key로 생성되는 st-key-* 클래스를 CSS 훅으로 써서 위젯을 뷰포트 모서리에 고정한다.
   위젯 자체는 정상 렌더 트리에 있어 동작하고, CSS는 위치만 바꾼다. */
.st-key-turf-chat-fab {
    position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 999999; width: auto !important;
}
.st-key-turf-chat-fab button {
    border-radius: 50% !important; width: 3.5rem; height: 3.5rem;
    font-size: 1.5rem; padding: 0 !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.22);
}
.st-key-turf-chat-panel {
    position: fixed; bottom: 5.6rem; right: 1.5rem;
    width: 390px; max-width: 92vw; max-height: 72vh; overflow-y: auto; overflow-x: hidden;
    z-index: 999999;
    background: var(--secondary-background-color, #ffffff);
    border: 1px solid rgba(120, 130, 140, 0.25); border-radius: 14px;
    padding: 0.6rem 1rem 0.9rem; box-shadow: 0 10px 34px rgba(0,0,0,0.20);
}
@media (max-width: 480px) {
    .st-key-turf-chat-panel { right: 4vw; left: 4vw; width: auto; bottom: 5rem; }
}
</style>
"""


def inject_base_styles() -> None:
    """앱 진입점에서 1회 호출."""
    st.markdown(_CSS, unsafe_allow_html=True)

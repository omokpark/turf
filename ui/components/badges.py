"""배지·신호등 표시 컴포넌트 — 관측 사실을 아이콘/색으로 빠르게 읽히게 한다.

판단 원칙 유지: 색·아이콘은 "좋다/나쁘다"가 아니라 관측된 사실의 방향·강도·
경과를 나타낸다 (예: 데이터가 오래됐다, 값이 수집 구역 내에서 두드러진다,
API 쿼터가 얼마나 남았다 — 전부 사실이지 추천이 아니다).

배지 문구는 업소명·주소 등 외부 데이터를 포함할 수 있으므로, HTML로 렌더링하는
모든 경로에서 반드시 html.escape()를 거친다 (2026-07-07 XSS 수정과 동일 원칙).
"""

import html
from datetime import datetime

import streamlit as st

WARN_KEYWORDS = ("폐업", "휴업", "주의")
GOOD_KEYWORDS = ("⭐", "확인", "심야")


def render_badges(badges: list[str]) -> None:
    """배지 문구 리스트를 알약 모양 칩으로 렌더링. 경고성 문구는 강조색."""
    if not badges:
        return
    chips = []
    for b in badges:
        cls = "turf-badge"
        if any(k in b for k in WARN_KEYWORDS):
            cls += " turf-badge-warn"
        elif any(k in b for k in GOOD_KEYWORDS):
            cls += " turf-badge-good"
        chips.append(f'<span class="{cls}">{html.escape(str(b))}</span>')
    st.markdown(f'<div class="turf-badge-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def percentile_signal(pct_top: float) -> str:
    """'수집 구역 내 상위 X%'의 강도를 신호등 색으로. 값이 클수록(더 상위) 진하게.

    좋다/나쁘다가 아니라 "얼마나 두드러지는 값인가"라는 통계적 사실만 표시한다.
    """
    if pct_top <= 10:
        dot = "🔴"
    elif pct_top <= 30:
        dot = "🟠"
    elif pct_top <= 60:
        dot = "🟡"
    else:
        dot = "⚪"
    return f"{dot} 수집 구역 내 상위 {pct_top:.0f}%"


def freshness_signal(freshness_dt: datetime | None, warn_days: int = 3, stale_days: int = 14) -> str:
    """데이터 수집 시점의 신선도를 신호등으로. 사실 표시일 뿐 품질 비난이 아니다."""
    if freshness_dt is None:
        return "⚪ 수집 시점 미상"
    age_days = (datetime.now() - freshness_dt).total_seconds() / 86400
    if age_days <= warn_days:
        dot = "🟢"
    elif age_days <= stale_days:
        dot = "🟡"
    else:
        dot = "🔴"
    return f"{dot} 수집 시점 {freshness_dt:%Y-%m-%d %H:%M} ({age_days:.0f}일 전)"


def quota_signal(sku_summary: dict) -> str:
    """Places 쿼터 잔여율을 신호등으로 (무제한 SKU는 표시 생략)."""
    parts = []
    labels = {
        "place_details_pro": "폐업검증",
        "place_details_enterprise": "평판스냅샷",
    }
    for sku, label in labels.items():
        info = sku_summary.get(sku, {})
        cap = info.get("한도")
        used = info.get("사용", 0)
        if not cap:
            continue
        remain_ratio = max(0.0, (cap - used) / cap)
        dot = "🟢" if remain_ratio > 0.5 else "🟡" if remain_ratio > 0.15 else "🔴"
        parts.append(f"{dot} {label} {used}/{cap}")
    return " · ".join(parts)

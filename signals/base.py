"""신호 플러그인 계약 — 업소 단위 Signal, 구역 단위 AreaIndicator

설계 원칙 (docs/REDESIGN_PLAN.md 1장):
- 새 분석 모델 추가 = 이 계약을 구현한 파일 1개 추가 + registry 등록. 그러면
  스코어러의 가용 신호 목록과 UI 배지에 코드 수정 없이 나타난다.
- requires에 명시한 데이터 소스가 없으면 자동 비활성 — 지역별 데이터 가용성
  차이(예: 서울 생활인구 vs 지방)를 구조로 흡수한다.
- 출력은 관측 사실만 담는다. 추천·예측 문구 금지 (CLAUDE.md 판단 원칙).
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pandas as pd

from core.area import Area

# ── Signal.compute 반환 DataFrame의 컬럼 계약 ────────────────────────────────
EST_ID = "업소ID"        # str: 통합 업소 테이블의 키 (matcher 도입 전에는 출처ID)
VALUE = "값"             # float: 0~1 정규화 점수 (스코어러 합성용)
RAW = "원시값"           # 원 단위 값 (업력 4.2년, 자리회전 3회 등)
BADGE = "배지문구"       # str|None: UI 배지 텍스트 — 관측 사실 문장. None이면 배지 없음
DETAIL = "상세"          # str: 근거 설명 (툴팁·확장 영역용)

SIGNAL_COLUMNS = [EST_ID, VALUE, RAW, BADGE, DETAIL]


@dataclass
class AreaContext:
    """신호·지표 계산에 필요한 모든 입력. rerun당 1회만 빌드한다.

    rosters: 소스별 원본 명부 {provider_id: DataFrame(ROSTER_COLUMNS)}
    establishments: 통합 업소 테이블 (matcher 도입 전에는 주 명부와 동일해도 됨)
    reference: 상대화 기준 명부 (같은 시군구 전체 등) — 구역 지표의 percentile 계산용.
               None이면 percentile은 생략된다.
    """

    area: Area
    establishments: pd.DataFrame
    rosters: dict[str, pd.DataFrame] = field(default_factory=dict)
    reference: pd.DataFrame | None = None
    today: pd.Timestamp | None = None  # 테스트 주입용. None이면 각 신호가 today() 사용

    @property
    def now(self) -> pd.Timestamp:
        return self.today if self.today is not None else pd.Timestamp.today()


@runtime_checkable
class Signal(Protocol):
    """업소 단위 신호 — '이 업소에 이런 관측 사실이 있다'."""

    id: str                 # "business_age"
    label: str              # UI 표시명: "업력"
    badge_icon: str         # "🌳"
    requires: frozenset     # 필요한 provider id 집합, 예: frozenset({"moi"})

    def compute(self, ctx: AreaContext) -> pd.DataFrame:
        """SIGNAL_COLUMNS 스키마의 DataFrame을 반환한다."""
        ...


@dataclass
class IndicatorResult:
    """구역 지표 1개의 계산 결과 (M0 아웃룩 카드 1장)."""

    current: float                      # 현재 기간 값
    previous: float | None              # 직전 기간 값 (비교 화살표용)
    series: pd.DataFrame | None         # 시계열 (차트용) — 지표마다 스키마 자유
    percentile: float | None            # 기준 명부(reference) 대비 백분위 0~100
    fact: str                           # 관측 사실 한 문장 — 판단 문구 금지


@runtime_checkable
class AreaIndicator(Protocol):
    """구역 단위 지표 — '이 구역의 흐름이 이렇다' (M0 아웃룩)."""

    id: str                 # "net_momentum"
    label: str              # "순증 모멘텀"
    requires: frozenset

    def compute(self, ctx: AreaContext) -> IndicatorResult: ...


def validate_signal_result(df: pd.DataFrame) -> None:
    """신호 출력 계약 검증 — 계약 테스트와 registry 통합 지점에서 사용."""
    missing = set(SIGNAL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Signal 출력 스키마 위반 — 누락 컬럼: {sorted(missing)}")
    if len(df) > 0:
        out_of_range = df[(df[VALUE] < 0) | (df[VALUE] > 1)]
        if len(out_of_range) > 0:
            raise ValueError(f"{VALUE} 는 0~1 범위여야 합니다 — 위반 {len(out_of_range)}행")

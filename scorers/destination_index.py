"""목적지 지수 (M1 Naver판) — DI = percentile(리뷰 모멘텀 R ÷ 입지 기대치 E)

핵심 컨셉의 코드화: 이면도로·낮은 밀집도에서 리뷰가 붙는 집 = 사람들이 "찾아가는" 집.
R는 review_momentum 신호의 원시값(log(1+블로그6개월)/업력), E는 같은 조건 코호트의
기대치다.

입지 기대치 E — 계획 원안은 SGIS 유동인구 십분위였으나 SGIS 인증키가 아직 없어
**주변 업소 밀집도 십분위를 유동 프록시**로 쓴다(반경 300m 내 영업 업소 수, 수집
데이터만으로 계산 가능). 코호트 = (업태 × 밀집도 십분위), 코호트 표본이 5 미만이면
업태 전체 → 구역 전체로 폴백. E의 바닥값을 두어 0-나눗셈과 소표본 폭주를 막는다.

블로그가 한 건도 없는 업소는 목적지 신호 자체가 관측되지 않은 것이므로 점수를 만들지
않는다 (배지 없는 점수 금지 계약과도 일치).
"""

import numpy as np
import pandas as pd

from core import area as area_mod
from core import schema
from scorers import base as scorer_base
from scorers.base import register_scorer
from signals import base as signal_base

DENSITY_RADIUS_M = 300
MIN_COHORT = 5
E_FLOOR = 0.05  # R 스케일(log1p(블로그)/업력)에서의 기대치 바닥값


def _density_decile(df: pd.DataFrame) -> pd.Series:
    """업소별 반경 300m 내 영업 업소 수의 십분위(1~10). 인덱스는 df와 동일."""
    coords = df.dropna(subset=[schema.LAT, schema.LON])
    lat = coords[schema.LAT].to_numpy()
    lon = coords[schema.LON].to_numpy()
    mdl = area_mod.meters_per_deg_lon(float(np.median(lat)))
    counts = []
    for i in range(len(coords)):
        dx = (lon - lon[i]) * mdl
        dy = (lat - lat[i]) * area_mod.METERS_PER_DEG_LAT
        counts.append(int(((dx * dx + dy * dy) <= DENSITY_RADIUS_M**2).sum()) - 1)
    deciles = pd.Series(counts, index=coords.index).rank(pct=True).mul(10).clip(1).round().astype(int)
    return deciles.reindex(df.index)


def _expectation_note(r) -> str:
    """기대치 E의 근거를 배지에 병기할 문구 — 어느 코호트 평균인지, 바닥값 발동 여부.

    바닥값이 발동한 경우 표시 배수는 R/바닥값이라 실제 코호트 기대치 대비보다 '작게'
    나온다(바닥값 > 코호트 평균이므로) — 배수가 하한값이라는 사실을 명시한다.
    """
    if r["E바닥"]:
        return f"비교군 평균이 바닥값({E_FLOOR}) 미만이라 바닥값으로 나눔 — 배수는 하한값"
    if r["E근거"] == "코호트":
        return f"기대치 = 같은 구간 {r['업태']} {r['E표본']}곳 평균"
    if r["E근거"] == "구간":
        return f"기대치 = 같은 구간 전체 {r['E표본']}곳 평균 (동일 업태 표본 {MIN_COHORT}곳 미만)"
    return f"기대치 = 구역 전체 {r['E표본']}곳 평균 (구간 표본 {MIN_COHORT}곳 미만)"


@register_scorer
class DestinationIndex:
    id = "destination_index"
    label = "목적지 지수 (Naver판)"
    description = (
        "리뷰 모멘텀(최근 6개월 블로그/업력)이 같은 업태·유사 밀집도 코호트의 기대치를 "
        "얼마나 초과하는지의 백분위. 낮은 밀집도(음영지역)에서 입소문이 붙는 집이 위로 온다. "
        "블로그가 관측되지 않은 업소는 제외. 코호트 표본이 적으면 밀집도 구간 → 구역 전체 "
        "평균으로 폴백하며, 어떤 기대치와 비교했는지를 각 배지에 병기합니다. "
        "블로그 수는 체험단·광고 캠페인으로 부풀 수 있습니다 — 배지의 건수·시점은 관측 사실 그대로입니다."
    )

    def score(self, signal_results: dict[str, pd.DataFrame], ctx) -> pd.DataFrame:
        review = signal_results.get("review_momentum")
        if review is None or len(review) == 0:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        est = ctx.establishments.set_index(schema.SRC_ID)
        review = review.set_index(signal_base.EST_ID)
        review = review[review.index.isin(est.index)]

        deciles = _density_decile(ctx.establishments).to_frame("십분위").set_index(
            ctx.establishments[schema.SRC_ID]
        )["십분위"]

        frame = pd.DataFrame(
            {
                "R": review[signal_base.RAW],
                "배지": review[signal_base.BADGE],
                "업태": est.loc[review.index, schema.CAT_S],
                "십분위": deciles.reindex(review.index),
            }
        )

        # 코호트 기대치: (업태 × 밀집도 십분위) → 같은 십분위 전체 → 구역 전체 순 폴백.
        # 폴백이 '업태 평균'이면 안 된다 — 음영지역 외톨이 업소(코호트 크기 1이 흔함)가
        # 번화가 강자들이 끌어올린 업태 평균과 비교당해, 정확히 찾으려는 대상(저밀집에서
        # 리뷰 붙는 집)이 눌린다. 십분위 폴백은 입지 수준을 통제한 기대치를 유지한다.
        #
        # 어느 단계 기대치와 비교했는지·바닥값이 발동했는지는 업소마다 다르다 — "기대치의
        # N배"라는 핵심 수치의 근거이므로 배지에 반드시 병기한다 (배지 없는 점수 금지
        # 계약의 정신: 근거가 보이지 않는 수치도 금지).
        area_mean = float(frame["R"].mean())
        decile_sizes = frame.groupby("십분위")["R"].transform("size")
        decile_mean = frame.groupby("십분위")["R"].transform("mean")
        cohort_sizes = frame.groupby(["업태", "십분위"])["R"].transform("size")
        cohort_mean = frame.groupby(["업태", "십분위"])["R"].transform("mean")
        use_cohort = (cohort_sizes >= MIN_COHORT) & cohort_mean.notna()
        use_decile = ~use_cohort & (decile_sizes >= MIN_COHORT) & decile_mean.notna()
        expectation = cohort_mean.where(use_cohort, decile_mean.where(use_decile, area_mean)).fillna(area_mean)
        frame["E근거"] = np.select([use_cohort, use_decile], ["코호트", "구간"], default="구역")
        frame["E표본"] = (
            np.select([use_cohort, use_decile], [cohort_sizes, decile_sizes], default=len(frame)).astype(int)
        )
        frame["E바닥"] = expectation < E_FLOOR
        frame["E"] = expectation.clip(lower=E_FLOOR)
        frame["DI원시"] = frame["R"] / frame["E"]

        # 블로그 미관측(R=0) 업소는 목적지 신호가 없다 — 제외
        frame = frame[frame["R"] > 0].copy()
        if len(frame) == 0:
            return pd.DataFrame(columns=scorer_base.SCORE_COLUMNS)

        frame["점수"] = frame["DI원시"].rank(pct=True).round(4)
        frame = frame.sort_values("점수", ascending=False).reset_index()
        frame["순위"] = frame.index + 1
        frame["근거배지목록"] = frame.apply(
            lambda r: [
                f"🎯 리뷰 모멘텀이 입지 기대치의 {r['DI원시']:.1f}배 "
                f"(밀집도 {int(r['십분위'])}/10 구간 · {_expectation_note(r)})",
                *([r["배지"]] if pd.notna(r["배지"]) and r["배지"] else []),
            ],
            axis=1,
        )
        out = frame.rename(columns={signal_base.EST_ID: scorer_base.EST_ID})
        return out[[scorer_base.EST_ID, scorer_base.SCORE, scorer_base.RANK, scorer_base.BADGES]]

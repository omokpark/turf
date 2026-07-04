"""인허가 데이터 기반 개폐업 시계열·영업 신호 집계

입력: license_fetcher.load_licenses()가 만든 정규화 DataFrame
출력: 전부 pandas DataFrame — 판단 문구 없이 신호만 집계한다 (CLAUDE.md 판단 원칙).
"""

import math

import pandas as pd


def filter_radius(df: pd.DataFrame, cx: float, cy: float, radius: int) -> pd.DataFrame:
    """중심 (cx, cy)에서 radius(m) 이내 행만 남긴다 (등장방형 근사)."""
    meters_per_deg_lon = 111_320 * math.cos(math.radians(cy))
    dx = (df["경도"] - cx) * meters_per_deg_lon
    dy = (df["위도"] - cy) * 111_320
    return df[(dx * dx + dy * dy) <= radius * radius].reset_index(drop=True)


def yearly_trend(df: pd.DataFrame, years: int = 10, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """최근 N년의 연도별 개업·폐업 건수. 반환: [연도, 개업, 폐업, 순증]"""
    today = today or pd.Timestamp.today()
    start_year = today.year - years + 1

    opened = df[df["인허가일자"].dt.year >= start_year].groupby(df["인허가일자"].dt.year).size()
    closed_dates = df["폐업일자"].dropna()
    closed = closed_dates[closed_dates.dt.year >= start_year].groupby(closed_dates.dt.year).size()

    all_years = range(start_year, today.year + 1)
    out = pd.DataFrame(
        {
            "연도": list(all_years),
            "개업": [int(opened.get(y, 0)) for y in all_years],
            "폐업": [int(closed.get(y, 0)) for y in all_years],
        }
    )
    out["순증"] = out["개업"] - out["폐업"]
    return out


def recent_openings(df: pd.DataFrame, days: int = 90, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """최근 N일 내 인허가를 받고 현재 영업 중인 업소 — 방문 골든타임 리스트."""
    today = today or pd.Timestamp.today()
    cutoff = today - pd.Timedelta(days=days)
    out = df[df["영업중"] & (df["인허가일자"] >= cutoff)].copy()
    out["개업경과일"] = (today - out["인허가일자"]).dt.days
    return out.sort_values("인허가일자", ascending=False).reset_index(drop=True)


def site_turnover(df: pd.DataFrame) -> pd.DataFrame:
    """자리 회전 신호: 같은 주소에서 폐업 이력이 있고, 현재 영업 중인 업소가 들어온 자리.

    반환: 현재 영업 중 업소 행 + [자리회전수(그 주소의 과거 폐업 건수)]
    주소 키는 도로명주소(없으면 지번주소)를 사용한다.
    """
    key = df["도로명주소"].where(df["도로명주소"].str.len() > 0, df["지번주소"])
    df = df.assign(_주소키=key.str.replace(r"\s+", " ", regex=True))
    df = df[df["_주소키"].str.len() > 0]

    closed_counts = df[~df["영업중"]].groupby("_주소키").size().rename("자리회전수")
    alive = df[df["영업중"]].join(closed_counts, on="_주소키")
    out = alive[alive["자리회전수"].notna()].copy()
    out["자리회전수"] = out["자리회전수"].astype(int)
    return (
        out.sort_values("자리회전수", ascending=False)
        .drop(columns=["_주소키"])
        .reset_index(drop=True)
    )


def business_age(df: pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """현재 영업 중 업소의 업력(년). 반환: 영업중 행 + [업력년]"""
    today = today or pd.Timestamp.today()
    out = df[df["영업중"]].copy()
    out["업력년"] = ((today - out["인허가일자"]).dt.days / 365.25).round(1)
    return out.reset_index(drop=True)

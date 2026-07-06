"""수집된 행안부 인허가 parquet 파티션의 읽기 전용 저장소

build_index.py가 만든 data/cache/moi/{업종}/{자치단체코드}.parquet 들을 합쳐
ROSTER DataFrame으로 제공한다. 파티션이 없으면 빈 명부 — UI가 수집 안내를 띄운다.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from core import config, schema

MOI_CACHE = config.CACHE_DIR / "moi"


def partition_files() -> list[Path]:
    if not MOI_CACHE.exists():
        return []
    return sorted(MOI_CACHE.glob("*/*.parquet"))


def load_roster(categories: list[str] | None = None) -> pd.DataFrame:
    """수집된 전 파티션(또는 지정 업종만)을 합친 ROSTER. 없으면 빈 명부."""
    files = partition_files()
    if categories is not None:
        files = [f for f in files if f.parent.name in categories]
    if not files:
        return schema.empty_roster()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    # 업종 파일 간 같은 업소 중복은 없지만(업종별 관리번호 상이), 재수집 겹침만 방어
    return df.drop_duplicates(subset=[schema.SRC_ID]).reset_index(drop=True)


def freshness() -> datetime | None:
    """가장 오래된 파티션의 수집 시점 — '데이터 기준일' 표기는 보수적으로 한다."""
    files = partition_files()
    if not files:
        return None
    return datetime.fromtimestamp(min(f.stat().st_mtime for f in files))


def cache_token() -> tuple:
    """캐시 무효화용 토큰 — 파티션이 추가·갱신되면 반드시 값이 바뀐다.

    freshness()는 '가장 오래된' 시각이라 새 파티션이 추가돼도 안 변한다(실제로
    단란주점만 보이던 버그의 원인). 파일 목록+수정시각 전체를 키로 쓴다.
    """
    return tuple(sorted((str(f), f.stat().st_mtime) for f in partition_files()))


def cached_summary() -> pd.DataFrame:
    """UI 안내용: 업종·자치단체별 보유 현황. [업종, 자치단체코드, 행수]"""
    rows = []
    for f in partition_files():
        rows.append({"업종": f.parent.name, "자치단체코드": f.stem, "행수": len(pd.read_parquet(f, columns=[schema.SRC_ID]))})
    return pd.DataFrame(rows)

"""Provider 공용 parquet 파일 캐시 — 격자 스냅 키 + TTL

st.cache_data(인메모리, 세션 수명)와 달리 프로세스 재시작을 넘어 살아남고,
격자 스냅 덕에 가까운 지점을 다시 조회해도 같은 셀이면 재호출이 없다.
파일은 data/cache/{provider_id}/ 아래에 쌓이며 TTL이 지나면 덮어쓴다.
"""

from datetime import datetime

import pandas as pd

from core import config
from core.area import FETCH_GRID_M, Area


def _cache_path(provider_id: str, area: Area, grid_m: int):
    gx, gy = area.grid_key(grid_m)
    return config.CACHE_DIR / provider_id / f"{gx:.6f}_{gy:.6f}_{area.radius}.parquet"


def fetch_cached(provider, area: Area, grid_m: int = FETCH_GRID_M) -> pd.DataFrame:
    """격자 스냅된 중심으로 provider.fetch를 호출하고 결과를 parquet으로 캐시한다.

    스냅은 캐시 키와 실제 조회 중심에 함께 적용된다 — 조회 반경(FETCH_RADIUS_M)이
    분석 최대 반경보다 스냅 오차 이상 넉넉해서(core.area 참고) 분석 결과는 달라지지 않는다.
    """
    path = _cache_path(provider.id, area, grid_m)
    if path.exists():
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        if age < provider.cache_ttl:
            return pd.read_parquet(path)

    gx, gy = area.grid_key(grid_m)
    df = provider.fetch(Area(cx=gx, cy=gy, radius=area.radius))
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df

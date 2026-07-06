"""행안부 인허가 데이터를 자치단체 단위로 수집해 parquet 파티션으로 저장하는 CLI

사용법:
  python -m datasources.build_index --district 3220000                  # 강남구, 3개 업종 전부
  python -m datasources.build_index --district 3220000 --category 일반음식점
  python -m datasources.build_index --district 3220000 --update         # 기존 파티션 증분 갱신

저장 경로: data/cache/moi/{업종}/{자치단체코드}.parquet
호출량 참고: 강남구 일반음식점 약 5.1만 행 = 약 511 호출 (일 한도 10,000의 5%).
"""

import argparse
import sys
from datetime import datetime

import pandas as pd

from core import config, schema
from datasources import moi_api


def partition_path(category: str, district_code: str):
    return config.CACHE_DIR / "moi" / category / f"{district_code}.parquet"


def build(district_code: str, category: str) -> pd.DataFrame:
    """자치단체 1곳 × 업종 1개 전체 수집 → parquet 저장 → DataFrame 반환."""
    def progress(page, total_pages, total_count):
        if page == 1 or page % 25 == 0 or page == total_pages:
            print(f"  [{category}] {page}/{total_pages} 페이지 (총 {total_count:,}건)", flush=True)

    df = moi_api.fetch_district(district_code, category, on_progress=progress)
    path = partition_path(category, district_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"  저장: {path} ({len(df):,}행)")
    return df


def update(district_code: str, category: str) -> pd.DataFrame:
    """증분 갱신: 파티션의 최근 인허가·폐업 시점 이후 변경분을 받아 관리번호 기준 upsert."""
    path = partition_path(category, district_code)
    if not path.exists():
        print(f"  [{category}] 파티션이 없어 전체 수집으로 전환")
        return build(district_code, category)

    existing = pd.read_parquet(path)
    # 갱신 기준: 보유 데이터의 최신 관측 시점 (인허가·폐업 중 늦은 쪽) 이후
    latest = max(
        existing[schema.LICENSED_AT].max(),
        existing[schema.CLOSED_AT].max() if existing[schema.CLOSED_AT].notna().any() else pd.Timestamp.min,
    )
    since = latest.strftime("%Y%m%d") + "000000"
    changed = moi_api.fetch_updated_since(category, since)
    # 전국 변경분에서 이 자치단체 것만 — 주소 prefix가 아니라 관리번호 prefix(자치단체코드)로 거른다
    changed = changed[changed[schema.SRC_ID].str.startswith(district_code)]
    if len(changed) == 0:
        print(f"  [{category}] 변경분 없음")
        return existing

    merged = (
        pd.concat([existing, changed])
        .drop_duplicates(subset=[schema.SRC_ID], keep="last")
        .reset_index(drop=True)
    )
    merged.to_parquet(path, index=False)
    print(f"  [{category}] 변경 {len(changed):,}건 반영 → 총 {len(merged):,}행")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="행안부 인허가 데이터 파티션 빌드")
    parser.add_argument("--district", required=True, help="개방자치단체코드 (예: 강남구 3220000)")
    parser.add_argument("--category", choices=list(moi_api.SERVICES), help="생략 시 3개 업종 전부")
    parser.add_argument("--update", action="store_true", help="기존 파티션 증분 갱신")
    args = parser.parse_args()

    categories = [args.category] if args.category else list(moi_api.SERVICES)
    started = datetime.now()
    for category in categories:
        print(f"{'갱신' if args.update else '수집'} 시작: {args.district} / {category}")
        df = update(args.district, category) if args.update else build(args.district, category)
        alive = int(df[schema.IS_OPEN].sum())
        print(f"  요약: 전체 {len(df):,}행, 영업중 {alive:,}, 폐업 등 {len(df) - alive:,}")
    print(f"완료 ({datetime.now() - started})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""콘솔 실행 진입점 (Day 1~2): 반경 내 경쟁 지형 출력"""

from analyzer.terrain import analyze
from collector.shop_fetcher import fetch_shops
from presenter.report import generate_report

# 테스트 좌표: 경복궁 근처
CX = 126.9769
CY = 37.5796
RADIUS = 500
MY_CATEGORY = "카페"


def main():
    shops = fetch_shops(CX, CY, RADIUS)
    result = analyze(shops, MY_CATEGORY)
    print(generate_report(result, RADIUS, MY_CATEGORY))


if __name__ == "__main__":
    main()

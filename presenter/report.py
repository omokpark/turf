"""경쟁 지형 문구 생성"""

from core import schema


def generate_report(result: dict, radius: int, my_category: str | None = None) -> str:
    """analyzer 집계 결과를 경쟁 지형 텍스트로 변환한다."""
    lines = [f"--- 반경 {radius}m 경쟁 지형 ---", f"총 음식점: {result['total']}곳"]

    for i, row in result["by_category"].iterrows():
        lines.append(f"{i + 1}위 {row[schema.CAT_S]}: {row['개수']}곳 ({row['비율']}%)")

    if my_category and result["my_rank"]:
        lines.append(
            f"★ 내 업종({my_category}): {result['my_count']}곳, "
            f"{result['my_rank']}위, {result['my_pct']}% 차지"
        )

    return "\n".join(lines)

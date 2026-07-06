"""식약처(식품안전나라) Open API 실검증 스크립트 — 사용자 PC(한국 네트워크)에서 실행.

목적: LOCALDATA 수동 CSV의 월중 공백을 메울 증분 갱신 채널로
식약처 식품접객업 계열 API가 실제로 쓸 만한지 확인한다.

확인 항목:
  1. openapi.foodsafetykorea.go.kr 에 이 PC에서 접속이 되는가
     (원격 샌드박스에서는 타임아웃 — 한국 밖 IP 차단으로 추정, 미확정)
  2. 폐업정보(I2819)가 문서 스펙대로 응답하는가 (인허가번호·폐업일자·주소 등)
  3. CHNG_DT(변경일자) 파라미터로 증분 조회가 실제로 동작하는가
  4. 전체 현황 계열 서비스의 응답에 위도/경도가 있는가
     (있으면 pyproj 좌표 변환 없이 바로 사용 가능)

사용법:
  1. https://www.foodsafetykorea.go.kr 회원가입 → 마이페이지 → Open API 인증키 신청
  2. .env 에 MFDS_API_KEY=발급키 추가 (키가 없으면 sample 키로 5건 맛보기만 실행)
  3. python scripts/verify_mfds_api.py
"""

import json
import os
import sys
import urllib.request

from dotenv import load_dotenv

load_dotenv()

BASE = "https://openapi.foodsafetykorea.go.kr/api"
KEY = os.getenv("MFDS_API_KEY", "sample")  # sample 키는 서비스당 5건 미리보기 제공

# 검증 대상 서비스. I2819(폐업정보)는 스펙 확인됨, 나머지는 후보 — 응답을 보고 판별.
SERVICES = {
    "I2819": "식품접객업 폐업정보 (스펙 확인됨: 인허가번호·업소명·업종·허가일자·폐업일자·주소)",
    "I2820": "후보: 식품접객업 인허가(현황) 계열로 추정 — 응답 필드 확인 필요",
    "I2810": "후보: 업체 인허가 현황 계열로 추정 — 응답 필드 확인 필요",
}


def call(service_id: str, params: str = "") -> dict | None:
    """API 1회 호출. 반환: 파싱된 JSON 또는 None(실패)."""
    url = f"{BASE}/{KEY}/{service_id}/json/1/5"
    if params:
        url += f"/{params}"
    print(f"  호출: {url.replace(KEY, '***')}")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:  # 접속 자체가 관건이므로 원인 종류를 그대로 보여준다
        print(f"  ✗ 접속 실패: {type(exc).__name__}: {exc}")
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"  ✗ JSON 아님 (앞 300자): {body[:300]}")
        return None


def inspect(service_id: str, desc: str) -> None:
    print(f"\n=== {service_id}: {desc} ===")
    data = call(service_id)
    if data is None:
        return
    svc = data.get(service_id)
    if svc is None:
        # 오류 응답은 {"RESULT": {"CODE": ..., "MSG": ...}} 형태로 옴
        print(f"  응답: {json.dumps(data, ensure_ascii=False)[:400]}")
        return
    result = svc.get("RESULT", {})
    rows = svc.get("row", [])
    print(f"  결과코드: {result.get('CODE')} / {result.get('MSG')}")
    print(f"  총 건수: {svc.get('total_count')}, 샘플 행: {len(rows)}건")
    if rows:
        first = rows[0]
        print(f"  응답 필드({len(first)}개): {list(first.keys())}")
        # 재설계 관점 핵심 체크: 좌표·영업상태·일자 필드 유무
        keys = " ".join(first.keys()).upper()
        for token, why in [
            ("LAT", "위도 → 있으면 pyproj 변환 불필요"),
            ("LON", "경도"),
            ("X", "X좌표(EPSG:5174 가능성)"),
            ("CLSBIZ", "폐업 관련"),
            ("PRMS_DT", "허가일자"),
            ("ADDR", "주소"),
        ]:
            mark = "✓" if token in keys else "✗"
            print(f"    {mark} {token}: {why}")
        print(f"  샘플 1건: {json.dumps(first, ensure_ascii=False)[:500]}")


def check_incremental() -> None:
    """CHNG_DT 증분 파라미터가 실제로 필터로 동작하는지 확인 (발급키 필요)."""
    print("\n=== 증분 조회(CHNG_DT) 동작 확인: I2819 ===")
    if KEY == "sample":
        print("  (건너뜀 — sample 키는 파라미터 조회 불가, MFDS_API_KEY 발급 후 재실행)")
        return
    data = call("I2819", "CHNG_DT=20260601")
    if data and (svc := data.get("I2819")):
        print(f"  2026-06-01 이후 변경분 총 건수: {svc.get('total_count')}")
        print("  → 이 숫자가 전체 건수보다 훨씬 작으면 증분 필터가 동작하는 것")


if __name__ == "__main__":
    print(f"인증키: {'발급키 사용' if KEY != 'sample' else 'sample 키 (서비스당 5건 미리보기)'}")
    for sid, desc in SERVICES.items():
        inspect(sid, desc)
    check_incremental()
    print("\n완료. 접속 실패가 반복되면 이 API 루트는 보류하고 LOCALDATA 수동 운영을 유지한다.")
    sys.exit(0)

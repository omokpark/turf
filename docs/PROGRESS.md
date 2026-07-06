# turf 진행 현황 요약

> 최종 갱신: 2026-07-07 (Day 11 종료 시점). 상세 이력은 `claude.md` 8장, 단계별 계획·체크박스는 `docs/REDESIGN_PLAN.md` 참고.

## 한 줄 정의

주류회사 영업사원이 담당 구역에서 **집중해야 할 업소를 찾아주는** 영업 인텔리전스 도구.
핵심 산출물 = 음영지역 숨은 잠재 업소(목적지 지수: 리뷰 모멘텀 ÷ 입지 기대치).

## 타임라인

| Day | 내용 | 상태 |
|---|---|---|
| 1~2 | 콘솔 엔진: collector(SEMAS 반경 상권조회) → analyzer(업종 집계) → presenter(텍스트) | ✅ |
| 3 | Streamlit + folium 지도 UI 최초 버전 | ✅ |
| 4~6 | VWorld 배경지도·지오코딩, 업종 다중선택, Altair 차트, 마커·범례 | ✅ |
| 7 | 탭 구조(지도/업종 구성), 업종 필터를 조회 후 필터로 이동, 지도 클릭=중심 이동 | ✅ |
| 8 | 조회 버튼 제거(완전 반응형), 원 드래그·엣지 리사이즈 UX 확정, 프리페치+로컬 필터 | ✅ |
| 9 | **서비스 피벗**(상권 조회 → 주류 영업 인텔리전스), timeline/ 인허가 시계열 엔진 | ✅ |
| 10 | 전면 재개정 계획(REDESIGN_PLAN.md), LOCALDATA 폐쇄 확인 → 행안부 OpenAPI 전환, 플러그인 골격(Phase 0·1), M0 구역 아웃룩(Phase 2) | ✅ |
| 11 | 무료 업소 모델 3종+랭킹(Phase 2b), app.py 분해(Phase 3), **Naver 평판 축·M1 목적지 지수(Phase 4)** | ✅ 구현 (육안 검증 잔여) |

## 재개정 Phase 현황 (REDESIGN_PLAN.md)

- **Phase 0 준비** ✅ — 행안부 인허가 OpenAPI 3종·Naver 검색 API 실호출 검증
- **Phase 1 골격** ✅ — core/(schema·config·area), Signal/AreaIndicator/Scorer/Provider 레지스트리, moi_api·build_index, pytest 기반
- **Phase 2 M0 구역 아웃룩** ✅ — 국면 차트(미러 막대) + 지표 카드 4종(순증·생존율·주류친화 전환·업력 구성; 공실 회복은 표본 부족으로 제외)
- **Phase 2b 무료 업소 모델** ✅ — M2 생존자·M4 프랜차이즈·M5 주류 인접성 + recent_opening(골든타임) + 가중합 랭킹, "변화"·"방문 우선순위" 탭
- **Phase 3 구조 정리** ✅ — app.py 573→70줄, ui/(state·sidebar·map_view·channels·components·pages), JS 격리(map_interactions.js), SEMAS Provider+파일 캐시, 골든 테스트
- **Phase 4 Naver 평판 축** ✅ 구현 — matching/(정규화·매처), datasources/naver.py, M8 버즈 모멘텀, **M1 목적지 지수 Naver판**, 랭킹 기준 선택 UI
- **Phase 5 확장 모델** ⬜ — M3 성장 모멘텀, M6 업종 전환 벡터, M7 야간 상권 지수, 증분 갱신, M4 전국 스캔
- **Phase 6 Places 완전판** ⬜ — M1 완전판·심야영업·폐업 교차검증 (결제 등록 필요, 투입 여부는 M1 Naver판 검증 후 결정)

## 랭킹 정책 (사용자 피드백으로 확정)

- **신규 개업(공급사 미확정)이 최우선** — recent_opening 가중 1.5, 180일 선형 감쇠
- 생존자 지수는 자리 평균 도달에서 포화(나이가 많다고 계속 오르지 않음), 가중 0.5
- 프랜차이즈는 점수 미반영(정보 배지만) — "요즘 대부분 프랜차이즈라 제외는 과함"
- 모든 점수는 근거 배지 필수(계약 테스트로 강제) — 판단 문구 없이 관측 사실만

## 주요 실측 결과 (강남역 400m, 2026-07-06)

- 인허가 데이터: 강남구 3개 업종 53,278행 (일반음식점 51,071 + 단란 1,546 + 유흥 661)
- 가중합 랭킹: 상위 1~12위 전부 2026년 개업(11~160일차), 13위부터 생존 검증 업소
- **목적지 지수(M1 Naver판): 6위 '지안식당' = 밀집도 1/10 구간에서 블로그 100건** — 음영지역 숨은 잠재 업소 가설의 첫 실물 사례
- 버즈 모멘텀(M8): 개업 98일차 블로그 100건(샐러링 강남역점) 등 골든타임 9곳 포착
- 테스트 71개 그린. Naver 블로그 캐시 674건(7일 TTL)

## 남은 확인 사항 (사용자)

1. **목적지 지수 상위권 육안 검증** — "🎯 방문 우선순위" 탭에서 랭킹 기준을 '목적지 지수'로 바꿔 상위권이 실제 "찾아가는 집"인지 확인 → **M1 가설 판단 → Places 결제 투입 여부 결정**
2. 구역 아웃룩 국면 방향이 아는 지역 2곳(뜨는 곳/죽는 곳)의 상식과 일치하는지

## 알려진 한계 (투명 공개)

- 블로그 수는 Naver display 100건 캡(log 스케일로 완화)
- 입지 기대치 E는 유동인구가 아니라 업소 밀집도 프록시(SGIS 키 확보 시 교체 예정)
- 프랜차이즈 판별은 수집 자치단체 범위 기준(전국 스캔은 Phase 5) — 점수 미반영이라 실해 없음
- 폐업 신고 지연으로 폐업 축이 6개월~1년 늦게 반영될 수 있음(지표 캡션에 기준일 표기)
- 체험단 블로그 인플레 미보정(포스팅 지속성 지표는 Phase 5+)

## 다른 PC에서 이어서 작업하기

```
git clone https://github.com/omokpark/turf.git && cd turf
cp .env.example .env   # SGIS_API_KEY, VWORLD_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 채우기
pip install -r requirements.txt
python -m datasources.build_index --district 3220000   # 인허가 데이터 재수집 (data/는 gitignore)
streamlit run app.py
```

⚠️ macOS에서 python.org 파이썬 사용 시 `Install Certificates.command`를 반드시 실행할 것 (미실행 시 행안부 API의 urllib 호출이 SSL 오류로 실패).

# turf 전면 재개정 계획 — 주류 영업 인텔리전스 플랫폼

> 작성: 2026-07-06 (Day 10). 각 Phase 완료 시 이 문서의 체크박스와 claude.md 진행 상황을 함께 갱신할 것.

## Context

Day 9에 서비스가 "상권 지형 조회"에서 **"주류회사 영업사원용 잠재 업소 발굴 도구"**로 피벗됐으나, 코드는 여전히 반경 내 업종 빈도 집계기에 머물러 있다. 핵심 자산인 timeline/(인허가 시계열 엔진)은 UI에 미연동 고립 상태, app.py는 555줄 단일 파일(인라인 JS ~120줄 포함), 스키마는 암묵적 한글 컬럼 계약(SEMAS `상호` vs LOCALDATA `사업장명`), 분석 모델을 추가할 자리가 없다.

이번 재개정의 목표: **"새 분석 모델 추가 = 파일 1개"가 되는 플러그인 구조**를 세우고, 그 위에 구역 아웃룩(M0) + 잠재 업소 발굴 모델 8종을 무료→유료 순으로 단계 탑재한다. 진행 방식은 하이브리드: 최소 골격만 세우고 무료 모델로 직행, 구조 정리는 가치 검증 후.

사용자 준비 확정: LOCALDATA CSV 수동 다운로드 + Naver 키 + 식약처 키 + Google Cloud 결제 등록 전부 진행.

---

## 1. 목표 아키텍처

### 디렉터리 구조 (최종형)

```
turf/
├── app.py                      # 얇은 진입점 (st.navigation)
├── core/
│   ├── schema.py               # ★ 정규화 스키마: 컬럼 상수·검증 (한글 컬럼명 유지, 리터럴 산재 금지)
│   ├── area.py                 # Area(cx,cy,radius) + 거리/격자/줌 유틸 (app.py·trend.py 중복 로직 흡수)
│   └── config.py               # .env, 경로, 상수 단일 출처
├── datasources/                # 데이터 수급 계층 (수동 CSV·API 동일 인터페이스)
│   ├── base.py                 # Provider 프로토콜 (id, kind, cache_ttl, fetch(area), freshness(area))
│   ├── registry.py
│   ├── cache.py                # parquet 파일 캐시 (격자키+TTL)
│   ├── semas.py                # 기존 collector/shop_fetcher 래핑
│   ├── moi_api.py              # ★ 행안부 인허가 조회서비스 API (구 LOCALDATA 대체, 완전 자동)
│   │                           #   정규화 로직은 timeline/license_fetcher에서 이식 (EPSG:5174 변환 등)
│   ├── build_index.py          # CLI: API 페이징 수집 → 시군구 파티션 parquet (초기 적재·주기 갱신)
│   └── naver.py                # Naver 지역/블로그 검색
│   # (mfds.py 식약처 증분은 행안부 API 일간 갱신 확인으로 보류 — 폴백 후보로만)
├── matching/
│   ├── normalize.py            # 상호명 정규화 (지점명·괄호·법인표기 제거)
│   └── matcher.py              # 상호명 유사도(rapidfuzz) × 거리 감쇠 → 통합 업소 테이블
├── signals/                    # ★ 신호 플러그인 — 파일 1개 추가 = 모델 1개 추가
│   ├── base.py                 # Signal 프로토콜 + AreaContext
│   ├── registry.py             # @register, available(providers) — 소스 없으면 자동 비활성
│   └── (모델별 파일들 — 아래 2장)
├── scorers/
│   ├── base.py                 # Scorer 프로토콜 — 반환에 근거배지목록 필수 (판단 원칙의 코드화)
│   ├── registry.py
│   ├── weighted_sum.py         # 가용 신호 가중합 베이스라인
│   └── destination_index.py    # 목적지 지수
├── ui/
│   ├── state.py  sidebar.py  map_view.py  channels.py
│   ├── map_interactions.js     # 인라인 JS 격리 (제거 아님 — 검증된 UX 자산)
│   ├── components/ (badges.py, charts.py, shop_table.py)
│   └── pages/ (outlook.py, explore.py, changes.py, ranking.py)  # 아웃룩이 첫 페이지
├── analyzer/ presenter/        # 유지 (schema 상수 사용으로 수정)
├── tests/                      # pytest + 합성 픽스처 + 골든 테스트
└── data/ (raw/ cache/)         # gitignore
```

### 핵심 인터페이스 (계약)

**core/schema.py** — 모든 프로바이더가 반환하는 공통 명부(ROSTER) 컬럼 상수:
`출처, 출처ID, 상호, 업종대/중/소, 도로명주소, 지번주소, 위도, 경도, 인허가일자, 폐업일자, 영업중, 소재지면적`
(LOCALDATA `사업장명`→`상호` 변환은 어댑터 책임. 이후 전 계층은 schema 상수만 사용)

**Signal 프로토콜** (업소 단위): `id, label, badge_icon, requires(필요 provider id 집합), compute(ctx) -> DataFrame[업소ID, 값(0~1), 원시값, 배지문구, 상세]`
→ requires 미충족 시 자동 비활성: 지역별 데이터 가용성 차이(서울 생활인구 vs 지방)를 구조로 흡수.

**AreaIndicator 프로토콜** (구역 단위, M0 아웃룩용): `id, label, requires, compute(ctx) -> IndicatorResult{현재값, 비교값(직전 기간), 시계열 DataFrame, 상대 percentile(시군구 대비), 사실문구}`
→ Signal과 같은 레지스트리 패턴. 이후 SGIS 인구 추이·지하철 승하차 추이 등 외부 구역 지표도 같은 자리에 추가.

**Scorer 프로토콜**: `score(signal_results, ctx) -> DataFrame[업소ID, 점수, 순위, 근거배지목록]`
→ 배지 없는 점수 행 금지(계약 테스트로 강제). 부분 데이터 내성 필수.

---

## 2. 분석 모델 포트폴리오 (M0 아웃룩 + 업소 모델 8종)

모든 모델 출력 = percentile 점수 + **관측 사실 배지**만 ("판단하지 않고 신호만" 원칙).

### M0. 구역 아웃룩 (업소 모델들의 앞단)

영업사원의 사고 흐름 "내 구역이 지금 어떤 판인가 → 그 판에서 어디를 갈까"의 첫 질문에 답하는 구역 국면 진단. **단일 점수로 뭉개지 않고**(판단으로 오독 방지) 2축 국면 매트릭스 + 지표 5개로 구성.

- **국면 매트릭스**: 개업 증감 × 폐업 증감 4사분면 (📈확장 / 🔄교체 활발 / 😴정체 / 📉수축). 최근 3~5년 궤적을 연도별 점 이동 경로로 표시 — "정체→확장 전환 중" 같은 흐름이 한눈에 보임.
- **상대화 원칙**: 절대치는 구역만으로 상승/정체를 말할 수 없음 → 전 지표를 같은 시군구(또는 전국) 대비 percentile로 병기. LOCALDATA가 전국 데이터라 무료로 가능.

| 지표 | 정의 | 읽는 법 |
|---|---|---|
| 순증 모멘텀 | 최근 12M (개업−폐업)/활성업소, 직전 12M 대비 + 36M 시계열 | 방향과 가속도 |
| 공실 회복 속도 ★ | 폐업 주소에 새 인허가가 들어오기까지 중앙값 일수, 최근 vs 과거 | 빈 자리가 빨리 채워짐 = 진입 대기 수요의 직접 증거 |
| 신규 생존율 추이 | 개업 코호트별 1년 생존율의 연도별 변화 | 상권 체력의 질적 신호 (개업 수만으론 안 보임) |
| 주류친화 전환율 | 신규 개업 중 주류친화 업태 비중 추이 | 밤형으로 변하는 중인가 (M6의 구역 집계판, 코드 공유) |
| 업력 구성 | 신생(2년 미만) vs 장수(7년+) 비중 | 젊은/성숙 상권 프로파일 |

전부 LOCALDATA 무료. 구현은 AreaIndicator 플러그인 5개 + `pages/outlook.py`. 아웃룩의 국면 결과는 업소 랭킹의 맥락 배지("확장 국면 구역의 신규 개업")로 재사용.

한계(투명 공개): 인허가일자 기반이라 매출 규모는 안 보임(업소 수의 흐름). 폐업 신고 지연으로 폐업 축이 6개월~1년 늦게 반영될 수 있음 → 지표 캡션에 데이터 기준일(`freshness()`) 항상 표기.

### 업소 단위 모델 8종

| # | 모델 | 한 줄 정의 | 데이터 | 비용 | 난이도 |
|---|------|-----------|--------|------|--------|
| M2 | **생존자 지수** | 그 자리·상권의 평균 생존기간 대비 얼마나 오래 버티는가. 자리회전 3회 주소의 4년차 = 입지를 실력으로 이긴 집 | LOCALDATA 단독 (trend.py의 business_age+site_turnover 조인) | 무료 | 하 |
| M4 | **프랜차이즈 판별** | 전국 CSV에서 정규화 상호 출현 빈도 → 독립 업소만 남긴 실효 타깃 리스트 (프랜차이즈=본사 일괄계약이라 방문 효율 낮음) | LOCALDATA 전국 1회 스캔 | 무료 | 하 |
| M5 | **주류 인접성 지수** | 반경 300m 단란·유흥·호프 밀도 = "술 마시러 오는 동선" 위인가. 단독 랭킹이 아닌 부스터로 사용 | LOCALDATA 단란·유흥주점 파일 (컬럼 동일, load_licenses 재사용) | 무료 | 하 |
| M3 | **상권 성장 모멘텀** | 격자 단위 최근 12개월 개업 가속도. 인허가는 소문보다 3~6개월 빠른 선행지표 → 경쟁사보다 먼저 진입 | LOCALDATA + SGIS(분모 정규화) | 무료 | 중 |
| M6 | **업종 전환 벡터** | 같은 주소의 업태 교체 이력(카페→호프 = 밤형으로 변하는 골목) + 격자 신규개업 업태 구성 변화 | LOCALDATA (주소키 강화 필요) | 무료 | 중 |
| M8 | **버즈 모멘텀** | 최근 개업 업소 중 블로그 포스팅이 붙기 시작한 집 — 개업 직후 = 주류 공급사 결정 시점이라 타이밍 가치 최대 | Naver 블로그 검색 (일 25,000 무료) | 무료(키) | 하~중 |
| M1 | **목적지 지수** (핵심) | DI = percentile(리뷰모멘텀 R ÷ 입지기대치 E). R = log(1+리뷰수)/업력 (Naver판: 최근 6개월 블로그 수). E = 동일 (업태×유동십분위) 코호트 중앙값, 지하/2층 토큰 페널티 | Naver판 무료 → Places 완전판 | 단계적 | 중~상 |
| M7 | **야간 상권 지수** | 밤에 사람이 있고 밤에 여는 정도 — 주간 유동 기준 기존 상권등급과 다른 주류 특화 지도. v1 = 주류친화 업태 비중 + 심야 지하철 승하차 (+서울 생활인구), v2 = +Places 심야영업 비중 | LOCALDATA/SEMAS + 지하철 + 서울API → Places | v1 무료 | 중 |

주요 함정과 대응(구현 시 반영): 배달 전문점(면적 하한 필터), 체험단 블로그 인플레(포스팅 지속성 사용, 2개월차 지속률 배지), 양수도 시 업력 리셋(상호 유사도 승계 추정), 흔한 상호 오카운트(업태 결합+예외 사전), 동명 업소 블로그 오매칭(주소 토큰 필터 필수), 소표본 격자 z-score 폭주(분모 하한 5).

### 데이터 소스 현황 (2026-07-06 재검증 — ⚠️ LOCALDATA 폐쇄 반영)

- **~~LOCALDATA CSV~~ → 행안부 인허가 조회서비스 OpenAPI (data.go.kr)**: localdata.go.kr은 **2026-04-16 폐쇄**, 공공데이터포털로 일원화됨. 인허가 195종이 전부 OpenAPI로 재개방 — 수동 CSV 다운로드 운영 자체가 불필요해짐(완전 자동화 가능).
  - 일반음식점 조회서비스: [data ID 15154916](https://www.data.go.kr/data/15154916/openapi.do)
  - 단란주점영업 조회서비스: data ID 15154883
  - 유흥주점영업 조회서비스: data ID 15154890
  - (필요 시 휴게음식점 15154921, 제과점영업 15155252 등 동일 계열)
  - 공통 스펙: REST, JSON+XML, **일간 갱신**, 무료, 트래픽 개발계정 10,000/일. 좌표는 여전히 EPSG:5174(→ 기존 pyproj 변환 로직 재사용).
  - **✅ 실호출 검증 완료 (2026-07-06, 기존 .env의 데이터포털 키로 3개 업종 모두 즉시 동작 — 추가 활용신청 불필요였음)**:
    - 엔드포인트: `https://apis.data.go.kr/1741000/{general_restaurants|singing_bars|entertainment_bars}/info`
    - 파라미터: `serviceKey, pageNo, numOfRows(max 100), returnType(json|xml)` + 필터 `cond[LCPMT_YMD::GTE/LT]`(인허가일자 범위), `cond[SALS_STTS_CD::EQ]`(영업상태), `cond[OPN_ATMY_GRP_CD::EQ]`(개방자치단체코드), `cond[DAT_UPDT_PNT::GTE/LT]`(갱신시점 — 증분), `cond[BPLC_NM::LIKE]`, `cond[ROAD_NM_ADDR::LIKE]`, `cond[BASE_DATE::EQ]`(기준일자 시점 상태)
    - 응답 필드: BPLC_NM(사업장명), BZSTAT_SE_NM(업태구분명), LCPMT_YMD(인허가일자), **CLSBIZ_YMD(폐업일자)**, SALS_STTS_CD/NM(영업상태), LCTN_AREA(소재지면적), ROAD_NM_ADDR/LOTNO_ADDR, CRD_INFO_X/Y(EPSG:5174), OPN_ATMY_GRP_CD, MNG_NO, DAT_UPDT_PNT 외 다수(종사자수·보증액·월세액 등)
    - 실측: 일반음식점 총 2,464,424건(폐업 1,732,263건 포함 — **과거 이력 전체 보존, 시계열 가능 확정**). 연도별 개업 필터 동작: 2023년 79,291 / 2024년 74,256 / 2025년 69,605건. 강남구(3220000) 51,071건. 단란주점 44,375건, 유흥주점 58,774건.
  - 트래픽 산식: numOfRows 최대 100 → 자치단체 1곳 전체 적재 ≈ 300~600 호출(일 한도 내 여유). **전국 전체 스캔(M4 프랜차이즈 판별)은 약 24,600 호출 → 3일 분할 배치 또는 운영계정 트래픽 증가 신청 필요.**
  - ⚠️ 신규 인허가 건은 좌표가 공백일 수 있음(2026-07-03 개업 건에서 확인) — 최근 개업 신호(골든타임)에는 VWorld 지오코딩 폴백 필요.
  - 유의: 구 파일 루트(file.localdata.go.kr)는 사망, data.go.kr의 구 파일데이터 페이지(15045016 등)도 그 죽은 링크를 가리키는 stale 상태.
- **식약처 식품접객업 API**: 위 행안부 API가 일간 갱신이므로 **증분 보완 채널로서의 필요성 소멸** — 보류. `scripts/verify_mfds_api.py`는 예비 폴백으로만 유지.
- **Naver**: 지역검색 일 25,000 무료 + 블로그 검색 → 리뷰 모멘텀 무료 프록시.
- **SGIS**: 격자 인구·사업체 무료 전국 → 입지 기대치 분모.
- **Google Places**: 유료(결제 등록 예정) → M1 완전판·M7 v2·폐업 교차검증.

---

## 3. 단계별 실행 계획 (하이브리드)

각 단계 종료 시 앱은 항상 동작 상태. 단계 = 커밋 단위.

### Phase 0 — 준비 — ✅ 완료 (2026-07-06)
- [x] 이 계획서를 `docs/REDESIGN_PLAN.md`로 저장.
- [x] ~~LOCALDATA CSV 3개 수동 다운로드~~ → 폐쇄 확인, 행안부 OpenAPI로 대체.
- [x] ~~API 활용신청~~ → 기존 `.env` 데이터포털 키로 **3개 업종 모두 즉시 호출 성공** (신청 불필요였음).
- [x] 엔드포인트·파라미터·응답 필드 실측 확정 (위 "데이터 소스 현황" 참고) → `datasources/moi_api.py` 설계 반영 준비 완료.
- [x] 사용자: Naver Developers 키 발급 → `.env`에 NAVER_CLIENT_ID/SECRET 추가, **실호출 검증 완료** (2026-07-06). 블로그 검색: postdate 필드 확인(M8 버즈 모멘텀 시계열에 사용 가능). 지역 검색: 카테고리("술집>맥주,호프")·좌표(mapx/mapy, WGS84×10⁷) 반환 — matcher 보조·업태 보정에 사용 가능. 유의: 지역 검색은 display 최대 5건.
- 참고: `.env`의 키 이름 `SGIS_API_KEY`는 실제로는 공공데이터포털 공용 인증키 — Phase 1의 `core/config.py`에서 `DATA_GO_KR_API_KEY`로 개명 예정(하위호환 유지).

### Phase 1 — 최소 골격 — ✅ 완료 (2026-07-06)
- [x] `core/schema.py`(ROSTER 컬럼 상수+검증)·`core/config.py`·`core/area.py`(Area+거리/격자 유틸).
- [x] `signals/base.py`+`registry.py`(Signal + AreaIndicator 프로토콜), `scorers/base.py`(배지 필수 계약 포함).
- [x] pytest 34개: trend 5함수·terrain·schema·area·registry 계약·moi normalize(실 응답 구조 기반).
- [x] `datasources/moi_api.py` + `build_index.py`: 페이징 수집(재시도·진행표시), ROSTER 정규화, 자치단체 파티션 parquet, `--update` 증분(DAT_UPDT_PNT) 지원.
- [x] 검증: pytest 그린 / 강남구 단란주점 1,546행 실수집 — ROSTER 계약 통과, 좌표 96.8% 보유(전부 강남 범위), 인허가 이력 1983~2025 + 폐업 1,374건(→ 시계열 확정), 주소 100% 강남구, 실데이터 yearly_trend 동작 / 앱 무변경(HTTP 200).
- 부산물: 원본 app.py `_snap_to_grid`의 잠재 결함 발견·수정 — 스냅 전 위도로 경도 스텝을 계산해 남북 수 m 이동에 경도 캐시 키가 흔들리던 것을, 위도 선(先)스냅으로 고정 (Phase 3에서 app.py 치환 시 자동 반영).
- 주의: 좌표 공백 행을 버리지 않고 유지하기로 정책 변경(구 license_fetcher는 제거) — 신규 인허가 건이 좌표 없이 오므로 골든타임 신호에서 지오코딩 폴백으로 살린다.

### Phase 2 — M0 구역 아웃룩 — ✅ 구현 완료 (2026-07-06), 육안 검증 1건 잔여
- [x] AreaIndicator 5개: `net_momentum.py`(순증), `vacancy_recovery.py`(공실 회복 속도), `cohort_survival.py`(신규 생존율), `liquor_shift.py`(주류친화 전환율), `age_mix.py`(업력 구성) + `signals/outlook.py`(주류친화 분류·국면 궤적·500m 격자 percentile).
- [x] **"📈 구역 아웃룩" 탭** 추가(app.py 패치는 import 1줄+탭 3줄): 국면 매트릭스(연도별 궤적, 최신 연도 강조, 사분면 라벨, 툴팁) + 지표 카드 5장(직전 기간 비교·percentile) + 지표별 근거·추이 expander. 개업/폐업 색 `#1a7f5c`/`#b3541e` (CVD 검증 통과).
- [x] 강남구 3개 업종 전체 탑재: 일반음식점 51,071 + 단란주점 1,546 + 유흥주점 661 = 53,278행 (호출 약 534회). 강남역 800m 실측: 이력 4,934건·영업중 1,345곳, 국면 궤적 2021교체활발→2023확장→2024·25수축, 지표 5개 전부 유의미한 값 산출.
- [x] 표본 부족 시 우아한 강등(이유를 fact로 명시) — 단란주점 단독 데이터로 확인.
- [ ] 사용자 육안 검증: 아는 지역 2곳(뜨는 곳/죽는 곳)에서 국면 매트릭스 방향이 상식과 일치하는지.
- 공실 회복 속도(vacancy_recovery)는 24개월 재입점 기한+완결 관측으로 측정을 고쳤으나, 연도별 재입점 표본이 적어(강남역 기준 연 10~30건) 중앙값 편차가 과대 → **아웃룩에서 제외 (사용자 결정, 2026-07-06)**. 코드·테스트는 유지, 등록 import만 해제 — Phase 5 주소키 건물 단위 정규화 후 재평가.

### Phase 2b — 무료 업소 모델 3종 + 우선순위 화면 — ✅ 구현 완료 (2026-07-06), 육안 스팟체크 잔여
- [x] signals: `survivor.py`(M2), `franchise.py`(M4), `liquor_adjacency.py`(M5) + 계획 외 추가 `recent_opening.py`(신규 개업 골든타임 — 180일 선형 감쇠).
- [x] `scorers/weighted_sum.py` + **"🔄 변화"·"🎯 방문 우선순위" 탭 추가** (`ui/changes_tab.py`·`ui/ranking_tab.py`, app.py 패치는 import 2줄+탭 배선). 변화 탭: yearly_trend 차트, 최근 개업(골든타임)·자리회전 리스트. 우선순위 탭: 랭킹 표 + 근거 배지(M0 국면을 캡션 맥락으로 병기) + 지도 마커.
- [x] 검증: pytest 56개 그린(신호 계약·수치·스코어러 배지 계약 포함, `tests/test_business_signals.py`), 강남역 400m 실데이터 종단 확인 — 상위 1~12위 전부 2026년 개업(11~160일차), 13위부터 생존 검증 업소.
- [ ] 실지역 1곳 상위 30건 육안 스팟체크 (사용자).
- **랭킹 정책 확정 (사용자 피드백 2026-07-06, 2회 반영)**: ① 초기 버전이 장수 업소 순위가 되는 문제 → `recent_opening` 신호 추가(가중 1.5, "개업 직후 = 공급사 결정 시점"이라는 M8 전제의 무료 선반영). ② 그래도 노포가 높고 프랜차이즈 제외가 과하다는 피드백 → 생존자 지수를 자리 평균 도달에서 **포화**(MAX_RATIO 2.0→1.0, 나이 단조성 제거)·가중 0.5로 인하, **franchise는 가중 0(점수 미반영, 체인 추정 정보 배지만)**. "독립 업소로 추정" 배지는 노이즈라 제거(체인일 때만 배지).
- 부산물: weighted_sum이 배지 None→NaN(truthy)을 배지로 수집하던 잠재 버그 수정(pd.notna 가드). 신규 인허가 건 대응 위해 python.org 파이썬의 Install Certificates 미실행 시 urllib SSL 실패함을 확인(트러블슈팅 기록 — moi_api는 urllib 사용).

### Phase 3 — 구조 정리 — ✅ 구현 완료 (2026-07-06), 브라우저 스모크 잔여
- [x] app.py(573줄) → 얇은 진입점(70줄) + `ui/` 분해: `state.py`(세션·UI 상수)·`sidebar.py`·`map_view.py`·`channels.py`(JS↔파이썬 채널 양끝 집약)·`components/{charts,shop_table}.py`·`pages/{explore,outlook,changes,ranking}.py`(기존 *_tab.py는 git mv). 인라인 JS는 `ui/map_interactions.js`로 격리(string.Template, $min_r/$max_r 주입). streamlit-folium `<0.28` 상한 고정(0.27.x 검증).
- [x] `datasources/semas.py`(shop_fetcher → ROSTER 어댑터, validate_roster 강제) + `cache.py`(격자 스냅 키+TTL parquet 파일 캐시 — 세션을 넘어 재사용, 강남역 450m 5,840행 캐시 히트 0.02s). explore 페이지·main.py Provider 경유 전환. `collector/categories.py` 삭제.
- [x] analyzer/terrain·presenter/report를 schema 상수로 전환(by_category 컬럼 '상권업종소분류명'→schema.CAT_S). analyze는 ROSTER DataFrame/list[dict] 겸용.
- [x] 골든 테스트: `tests/test_semas.py` — Provider 경유 == 직접 호출 집계 동일(합성), 격자 캐시 재사용/TTL 만료. **실 API 골든**: main.py가 Day 1 콘솔 출력과 완전 동일(경복궁 500m 총 232곳, 카페 61곳 26.3% 등). pytest 60개 그린.
- [x] Day 8 확정 동작 브라우저 스모크(사용자 확인 2026-07-06): 원 드래그, 엣지 리사이즈 50m 스냅, 원 밖 클릭 점프, 업종 필터, CSV, 재분석 토스트.

### Phase 4 — 평판 축 (Naver) — ✅ 구현 완료 (2026-07-06), 육안 검증·임계 튜닝 잔여
- [x] `matching/normalize.py`(법인·괄호·말미 지점명 제거, 과제거 시 원형 유지 — franchise의 임시 정규화를 단일 출처로 이관) + `matcher.py`(30m 격자 블로킹, rapidfuzz×거리 감쇠 0.7:0.3, 60m 거리 상한, 1:1 greedy, 임계 0.82 보수적). rapidfuzz 의존성 추가.
- [x] `datasources/naver.py`: 블로그 검색 + **주소 토큰 필수**(지번 동 > 도로명 로/길 > 구 — 동명 업소 오매칭 방어, 토큰 없으면 조회 안 함) + 7일 파일 캐시 + 0.06s 레이트 슬립·재시도.
- [x] signals: `buzz_momentum.py`(M8 — 골든타임 180일 이내만 조회, 쿼터 방어를 테스트로 강제), `review_momentum.py`(R = log(1+블로그 6개월)/업력년, VALUE=반경 내 백분위) → `scorers/destination_index.py`(M1 Naver판).
- [x] **M1 입지 기대치 E의 설계 변경**: 원안 SGIS 유동 십분위 → SGIS 키 부재로 **주변 업소 밀집도 십분위(300m) 프록시**. 코호트 폴백 사슬 = (업태×십분위) → 같은 십분위 전체 → 구역 전체 — 업태 평균 폴백은 음영지역 외톨이 업소를 번화가 평균과 비교해 눌러버리는 결함이 테스트에서 확인되어 배제. 블로그 미관측(R=0) 업소는 점수 제외(배지 없는 점수 금지와 일치).
- [x] ranking 탭: 랭킹 기준 선택(가중합 ↔ 목적지 지수 radio), Naver 키 있으면 평판 신호 자동 활성(providers 가용성), 스피너 안내. pytest 71개 그린.
- [x] 강남역 400m 실측: 영업 453곳 전수 조회(7일 캐시 674건 적재), 블로그 관측 421곳. 목적지 지수 상위에 **밀집도 1/10 구간에서 블로그 100건인 '지안식당'** 등장 — 음영지역 숨은 잠재 업소 가설의 첫 실물 사례. 버즈 모멘텀: 개업 98일차 블로그 100건(샐러링) 등 골든타임 9곳 포착.
- [ ] 매칭 수작업 라벨 50쌍으로 임계 튜닝 (matcher가 통합 업소 테이블에 실사용되는 시점에).
- [ ] 목적지 지수 상위권 육안 검증(사용자) → **M1 가설 판단 → Places 결제 투입 여부 최종 결정.**
- 한계(투명): 블로그 수는 display 100 캡(log로 완화), E는 유동이 아니라 업소 밀집도 프록시(SGIS 키 확보 시 교체), 체험단 인플레 미보정(포스팅 지속성은 Phase 5+).

### Phase 5 — 확장 모델 + 증분 갱신
- [ ] signals: `growth_momentum.py`(M3), `conversion_vector.py`(M6, 주소키 강화 포함), `night_index.py`(M7 v1).
- [ ] `datasources/mfds.py`: 식약처 증분(Phase 0 실검증 통과 시) — load 후 upsert.
- 검증: 각 신호 추가가 기존 파일 수정 없이(등록 외) 이뤄지는지 = 아키텍처 최종 시험.

### Phase 6 — Places 완전판
- [ ] `datasources/places.py`: M1 완전판(리뷰 수·평점), M7 v2(심야영업), M2 폐업 교차검증("헛걸음 제거").
- 비용 통제: 무료 신호로 1차 후보 추린 뒤 상위 N건만 조회하는 2패스 + 격자 캐시 30일.

### 의존성 추가 시점
`pytest`(P1), `pyarrow`(P1), `rapidfuzz`(P4). matplotlib은 requirements에서 제거(미사용 확정).

---

## 4. 위험 요소

1. **매칭 오병합** → 보수적 임계 + 미병합 시 양쪽 독립 유지 + SOURCES 근거 추적.
2. ~~LOCALDATA 수동 의존~~ → **해소** (행안부 API 일간 갱신·완전 자동화). 잔여 위험: 신규 API의 페이지 크기·전국 스캔(M4) 트래픽 한도(개발계정 10,000/일) — 활용신청 후 실측으로 확정, 부족 시 운영계정 트래픽 증가 신청.
3. **JS 핵 취약성** → 격리 + 버전 고정 + 스모크 체크리스트를 회귀 게이트로.
4. **Naver/Places 쿼터·비용** → 2패스 조회 + 파일 캐시 TTL.
5. **판단 원칙 위반 오독** → Scorer 계약에 배지 필수 명시, 계약 테스트로 강제. 컷오프/추천 문구 금지 유지.

## 5. Critical Files

- `app.py` — Phase 2 탭 추가, Phase 3 분해 원본 (세션 키 10개·JS 채널 로직 보존)
- `timeline/trend.py` — M2/M3/M6/M8 이식 원천 (5함수)
- `timeline/license_fetcher.py` — LOCALDATA 어댑터 내부 구현, 단란·유흥 파일 추가 로드
- `collector/shop_fetcher.py` — SEMAS 어댑터 원천, 스키마 기준 컬럼
- `claude.md` — 각 Phase 종료 시 진행 상황 갱신 (다음 세션 재개용 관례 유지)

## 6. 전체 검증 방법

- 단위: pytest (신호·스코어러 계약 테스트 포함 — 전 신호 공통 스키마, 배지 없는 점수 금지).
- 동등성: 리팩토링 전후 골든 테스트 (고정 좌표 결과 일치).
- E2E: `streamlit run app.py` → 강남역 자동 조회 → 아웃룩/변화/우선순위 탭 → 실지역 상위 30건 육안 스팟체크.
- UI 회귀: Day 8 확정 동작 스모크 체크리스트 (문서화하여 매 Phase 반복).

한 줄 정의: 주류회사 영업사원이 담당 구역에서 **집중해야 할 업소를 찾아주는** 영업 인텔리전스 도구.

핵심 컨셉 (Day 9에 확정된 서비스 피벗):
- 영업사원은 자기 구역의 "잘되는 곳"은 이미 안다. 이 도구가 이기는 지점은 **회색지역·음영지역의 숨은 잠재 업소** — 수요 신호(평판·생존력)가 입지 기대치(노출·유동)를 크게 초과하는 곳.
- **목적지 지수** = 리뷰 모멘텀 ÷ 입지 기대치(유동인구·밀집도·대로변 여부). 이면도로·지하·2층에서 리뷰가 붙는 집 = 사람들이 찾아가는 집.
- 보조 신호: 신규 개업·업종 전환·자리 회전(인허가), 심야 영업·폐업 교차검증(Google Places), 죽은 자리의 생존자(업력), 영업장 면적, 층수·도로 위계(노출도 프록시).
- 외부 데이터만 사용한다 (회사 내부 거래처·주문 데이터 결합 없음).

판단 원칙 (수정됨): 창업 판단("들어갈까/버틸까")은 여전히 하지 않는다. 다만 **영업 방문 우선순위 신호는 랭킹한다** — 점수의 근거(배지)를 항상 투명하게 함께 보여준다.

로드맵:
- A. timeline/ — 행안부 인허가 데이터: 신규·폐업·전환·자리회전·업력·면적 (무료, 키 불필요, 백본) ← 진행 중
- B. collector/places_fetcher — Google Places: 평점·리뷰 모멘텀·심야영업·폐업검증 (Google Cloud 키+결제등록 필요) + matcher(상호명+좌표 매칭)
- C. scorer/ — 목적지 지수 중심 "음영지역 숨은 잠재 업소" 랭킹 + 근거 배지 리포트
- D. 유동인구 컨텍스트 레이어 — 서울 생활인구(열린데이터광장 키 필요): 야간 인구 지수, 추세. 서울 외 지역은 지하철 승하차 프록시.


1. 프로젝트 구조

turf/
├── .env                  ← API 키 (비공개)
├── .env.example          ← API 키 템플릿 (공개)
├── .gitignore
├── requirements.txt
├── CLAUDE.md             ← 이 파일
│
├── collector/
│   ├── shop_fetcher.py   ← 상가정보 API 호출
│   ├── geocoder.py       ← 주소·지번 → 좌표 변환 (VWorld)
│   └── categories.py     ← 전국 공통 음식 업종 소분류 목록 조회 (SEMAS)
│
├── analyzer/
│   └── terrain.py        ← 업종별 집계·통계 (food_df도 함께 반환, 지도 마커용)
│
├── presenter/
│   └── report.py         ← 경쟁 지형 문구 생성
│
├── timeline/             ← Day 9 착수 (엔진 완성, UI 연동·실데이터 검증 대기)
│   ├── license_fetcher.py ← LOCALDATA 인허가 CSV 로드·정규화 (EPSG:5174→WGS84)
│   └── trend.py           ← 개폐업 시계열·신규개업·자리회전·업력 집계
├── data/                 ← 인허가 CSV 등 대용량 원본 (gitignore, 수동 다운로드)
│
├── app.py                ← Streamlit 지도 UI (Day 3~6, 아래 8번 참고)
└── main.py               ← 콘솔 실행 진입점 (Day 1~2)


2. 기술 스택

항목선택언어Python 3.11+API (스냅샷)소상공인시장진흥공단 상가(상권)정보 API (data.go.kr)API (지도·지오코딩)VWorld 오픈API (배경지도 타일 + 주소검색)API (시계열, 미착수)행정안전부 일반음식점 인허가 데이터 (data.go.kr, CSV 파일)데이터 처리pandas시각화Altair (Streamlit 내장, st.altair_chart — 당초 계획한 matplotlib 대신 채택)지도 UIStreamlit + folium/streamlit-folium (Day 3~6)실행 환경로컬 → GitHub Actions (안정화 후)보안.env + .gitignore


3. 모듈 간 데이터 흐름

단계모듈 → 입력 → 출력① 획득 (스냅샷)collector/ — (cx, cy, radius) → 상가업소 리스트 [{상호, 업종, 위도, 경도}]② 정리analyzer/ — 상가업소 리스트 → 음식점만 필터된 DataFrame③ 집계analyzer/ — DataFrame → {업종별 개수, 비율, 내 업종 순위}④ 출력presenter/ — 집계 결과 → 경쟁 지형 텍스트① 획득 (시계열)timeline/ — CSV 파일 → 인허가 DataFrame [{업소명, 업종, 행정동, 인허가일자, 폐업일자, 영업상태}]② 집계timeline/ — DataFrame → 행정동·업종·연도별 개업·폐업 수③ 출력timeline/ — 집계 결과 → 연도별 추이 차트

핵심 원칙: 각 모듈은 입·출력만 약속한다. 내부 구현은 독립적으로 교체 가능.


4. 인터페이스 약속

입력


cx: float — 중심 경도 (예: 126.9769)
cy: float — 중심 위도 (예: 37.5796)
radius: int — 반경 미터 (예: 500)
my_category: str (선택) — 내 업종명 (예: '카페', '한식')


출력 구조


반경 내 음식점 총 개수
업종별 개수·비율 (많은 순 정렬)
내 업종: N곳, 전체 중 X위, 비중 Y%
한 줄 지형 요약 문구



5. 환경 설정

.env

SGIS_API_KEY=발급받은_서비스키
VWORLD_API_KEY=발급받은_서비스키   # 배경지도 타일 + 주소·지번 검색 (vworld.kr, 도메인 localhost 등록 필요)

.gitignore

.env
__pycache__/
*.pyc
.DS_Store
venv/

requirements.txt

requests>=2.31
pandas>=2.0
python-dotenv>=1.0
streamlit>=1.30      # Day 3
folium>=0.15         # Day 3
streamlit-folium>=0.18 # Day 3
matplotlib>=3.8      # Day 4 계획했으나 실제로는 Altair(Streamlit 내장) 사용, 현재 미사용


5-1. 다른 PC에서 이어서 작업하기

.env는 .gitignore에 포함되어 GitHub에 올라가지 않는다. 새 PC에서는 저장소를 clone해도 .env가 없으므로 직접 만들어야 한다.

git clone https://github.com/omokpark/turf.git
pip install -r requirements.txt
.env.example을 .env로 복사하고 SGIS_API_KEY, VWORLD_API_KEY 둘 다 채우기

data.go.kr / vworld.kr 서비스키는 PC·IP에 묶이지 않고 계정 단위로 발급된다. 기존에 쓰던 키를 그대로 재사용하면 되고, 새로 발급받을 필요는 없다. 단, VWorld 키는 발급 시 등록한 도메인(localhost 등)에서만 배경지도 타일이 정상 로드된다.


6. 보안 체크리스트


API 키: 코드에 직접 넣지 않는다. 반드시 .env로 분리.
호출량: 반경이 넓으면 페이지 단위로 결과가 나뉜다. 테스트는 반경 300~500m로 시작.
개인정보: 상호·주소는 공개 사업장 정보. 화면 출력·개인 사용은 안전.



7. 개발 금지 패턴


판단 문구 삽입 금지: '여기는 창업하기 좋습니다' 같은 추천·예측 문구는 넣지 않는다.
UI 먼저 금지: 엔진(collector → analyzer → presenter)이 먼저 완성돼야 한다. 지도는 Day 3.
반경 무제한 금지: 첫 테스트는 500m 이하. API 호출 한도 소진 방지.


8. 진행 상황 (다음 세션 재개용)

Day 1~2: collector(shop_fetcher) → analyzer(terrain) → presenter(report) 엔진 완성. main.py 콘솔 실행 확인.

Day 3: Streamlit + folium 지도 UI 최초 버전 (강남역 기본 위치, 지도 클릭으로 위치 지정, 반경 슬라이더, 업종 텍스트 입력, 막대 차트).

Day 4~6 (app.py 대폭 개편, 이번 세션에서 진행):
- VWorld 배경지도 타일 + 주소/지번 지오코딩 연동 (collector/geocoder.py 신규).
- 업종을 전국 공통 표준 목록(collector/categories.py 신규, SEMAS smallUpjongList)에서 다중 선택 가능하도록 변경, 현재 지역 빈도순 정렬.
- 조회조건 흐름을 "① 주소 → ② 지도에서 위치·반경 잡기(확정 버튼 없음, 화면 중앙 십자선+반경 미리보기 원이 지도와 함께 붙어서 움직임) → ③ 업종 선택 → ④ 찾기" 4단계로 단순화. 예전의 "중심점 확정/반경 확정" 버튼 2개는 제거함 (조작이 너무 많다는 피드백 반영).
- 검색 결과가 있을 때는 지도에 선택한 업종의 업소만 마커로 표시(전체 밀집도는 기본으로 안 보여줌), 업종별 색상 구분 + 범례, 업소 수가 적으면 클러스터링 생략·많으면 클러스터링 유지, 마커 클릭 시 상호명·업종명 팝업, 줌 레벨 17 이상에서는 hover 없이도 상호명이 항상 보임(LABEL_ZOOM_THRESHOLD 상수).
- 반경 내 업종 비교를 st.bar_chart 대신 Altair 가로 막대 차트로 교체 (순위+업종명 라벨, 개수·비율 동시 표시, 내가 고른 업종만 강조색). 기존 텍스트 리포트는 "원본 리포트 텍스트" 접이식(expander)으로 이동. 지도 아래에 정렬 가능한 업소 목록 표 추가.
- 검색 결과가 이미 있을 때는 지도 중앙 십자선+빨간 미리보기 원을 숨기고 확정된 파란 원만 표시 (줌 배율을 크게 바꾸면 두 원이 어긋나 보이는 문제 해결).
- 타이틀("공공API기반의 상권분석")을 메인 화면 상단 큰 제목에서 사이드바 맨 위 작은 제목으로 이동 (공간 절약).

Day 7 (app.py 재작성 — 입력 단순화 + 탭 구조, 이번 세션에서 진행):
- 조회 조건을 "① 위치(주소/장소 검색) → ② 반경 → ③ 조회하기" 3단계로 축소. 업종 선택은 조회 조건에서 제거하고 **조회 후 결과 필터(multiselect)**로 이동 — 결과에 실제 존재하는 업종만, 개수 많은 순으로 "업종명 (N곳)" 형태로 표시.
- 이에 따라 조회 전 업종 빈도 미리보기용 사전 API 호출(50m 격자 스냅 캐시) 삭제 → 지도 조작 중 API 호출 0회. collector/categories.py는 앱에서 더 이상 사용하지 않음(모듈은 유지).
- 지도는 표시 전용으로 재정의. 중심 미세조정은 드래그 추적(live_center) 대신 "지도 클릭 = 중심 이동"(st_folium last_clicked, 마커 클릭은 last_object_clicked와 비교해 제외, 처리한 클릭은 processed_click 세션 키로 중복 방지).
- 결과 화면을 st.tabs 2개로 분리: 🗺️ 지도(전체 음식점 밀집도 HeatMap + 선택 업종 마커 + LayerControl 토글 + 범례) / 📊 업종 구성(총계·선택 업종 지표·Altair 차트·업소 목록·CSV·리포트 expander). 업종 필터는 두 탭에 모두 영향을 주므로 탭 위에 배치.
- 위치·반경이 마지막 조회와 달라지면 "다시 조회하세요" 경고 표시(결과는 유지). 주소 검색으로 크게 이동하면 결과 초기화.
- 반경 원의 feature_group_to_add + 레이어 정리 JS 핵은 유지(반경 슬라이더 조작 시 지도 리마운트 방지 목적). live_center·_snap_to_grid·조회 스냅샷 비교 로직은 삭제.
- 버그 수정: analyzer/terrain.py — 반경 내 업소 0곳이면 KeyError 나던 것을 columns 명시로 해결. collector/shop_fetcher.py — lat/lon 누락 항목 skip.
- .claude/launch.json 추가 (Claude Code 프리뷰용 streamlit 실행 설정).

Day 8 (조회 버튼 제거 — 완전 반응형 전환, 이번 세션에서 진행):
- '조회하기' 버튼 삭제. 위치가 정해지면 **최대 반경(500m)으로 1회만 프리페치**(_load_area_shops, 5분 캐시)하고, 반경 슬라이더는 API 재조회 없이 **로컬 거리 필터**(_within_radius, 등장방형 근사)로 즉시 반영. "조건이 바뀌었습니다" 경고도 함께 삭제(항상 최신 상태이므로).
- 앱 접속 즉시 기본 위치(강남역) 결과가 자동 표시됨.
- 반경 슬라이더를 도보 상권 기준으로 재조정: 최소 100 / 기본 300 / 최대 500m (스텝 50), "300m ≈ 도보 약 4분" 캡션 병기 (WALK_SPEED_M_PER_MIN=70).
- 주소 검색 후보를 selectbox+선택 버튼(3클릭)에서 **버튼 나열(1클릭, 최대 5개)**로 변경. 검색어와 이름이 정확히 일치하는 후보(예: '삼성역' 역 자체)를 퍼지 매칭 주소보다 앞에 정렬.
- 업종 필터 확정 사항: 기본값 전체(비움), 정렬 개수순 + "(N곳)" 라벨. 위치 이동 시 선택 유지(새 지역에 없는 업종만 자동 제거).
- 반경 원을 base map에 직접 그리도록 단순화 — Day 4~7의 feature_group_to_add + 레이어 정리 JS 핵(1px GIF onload) 완전 삭제. 반경 변경 시 지도가 리마운트되지만 API 호출이 없어 수용.
- 검증: 삼성역 검색→이동→자동 조회, 반경 100/300/500m 로컬 필터 결과가 API 직접 호출과 일치 확인.
- (후속 확정) 최대 반경 500→**400m**로 축소. 지도 줌을 fit_bounds에서 **반경 연동 고정 줌**(_zoom_for_radius: 반경 ≤200m → 줌 17, 그 외 줌 16)으로 교체 — fit_bounds는 요구 박스가 화면을 조금만 넘쳐도 줌을 한 단계 내려버려(줌 15) 원이 화면 1/4만 차지하는 "허한" 문제가 있었음. 이제 반경 원 지름이 지도 높이(560px)의 절반~3/4을 채움.
- (후속 확정) 레이아웃 재배치 — "컨트롤은 피드백 옆에" 원칙: **사이드바 = 검색·필터 패널**(① 주소 검색 ② 업종 필터), **지도 탭 = 반경 슬라이더(지도 바로 위, 도보 분 병기) + 지도**. 반경 상태는 위젯 키 radius_slider가 단일 소스.
- (후속 확정) **원 가장자리 드래그로 반경 조절(엣지 리사이즈)** 추가 — 가장자리 ±12px 밴드에서 잡으면 리사이즈 모드(방향별 resize 커서), 안쪽이면 중심 이동 모드(grab 커서). 끄는 동안 실시간 반영, 놓으면 50m 스텝·100~400m로 스냅. ⚠️ 새 반경 값의 파이썬 전달은 **last_object_clicked_tooltip 채널**: JS가 핀 툴팁에 "TURF_RADIUS:값:논스"를 심고 핀 click을 합성하면 streamlit-folium이 클릭된 객체의 툴팁 텍스트를 돌려줌(프론트엔드 onLayerClick이 모든 레이어에 바인딩됨을 소스로 확인). 논스로 중복 적용 방지, 수신 시점엔 슬라이더 위젯이 이미 그려져 있어 pending_radius에 담아 rerun 후 스크립트 상단에서 radius_slider에 반영.
- (후속 확정) 조건 변경(원 드래그·클릭·반경·주소 검색)으로 재분석되면 **완료 토스트**("📍 재분석 완료 — 반경 Nm 내 음식점 N곳", 주소 검색 시 "'장소명' 기준 " 접두)를 띄움 — 지도 리마운트 깜빡임이 오류로 오인되는 문제 대응. analysis_key(cx,cy,radius) 변화를 세션에 추적, 첫 로드는 조용히. 기존의 "위치 이동" 토스트는 이 토스트에 통합.
- (후속 확정) 중심 지정 UI를 여러 차례 시험 끝에 **"지도 고정 + 파란 원(영역 전체)을 잡아 드래그"**로 최종 확정. 원 내부 아무 곳이나 잡으면 커스텀 드래그 시작 — ⚠️ 반드시 **네이티브 pointerdown을 path 요소에서 직접** stopPropagation해야 함(Leaflet 1.9는 Browser.touch=true라 지도 팬을 pointerdown에서 시작하므로, Leaflet 레이어 mousedown 이벤트에서 막으면 이미 늦어 지도가 대신 끌림 — 실제로 이 버그를 겪고 고침). pointermove 델타만큼 원+십자 핀 이동, cursor grab/grabbing — streamlit-folium이 도형 드래그 좌표를 파이썬으로 돌려주지 않는 한계는, 놓는 순간 원 중심 좌표로 **지도 click 이벤트를 JS로 합성**해 last_clicked 채널로 우회. 드래그 직후 브라우저 잔여 click은 캡처 단계에서 1회 삼킨 뒤 60ms 후 합성 click 발사(잔여 click이 last_clicked를 덮어써 이동이 무시되는 레이스 방지). 십자 핀 자체도 draggable(동일 커밋 경로), 원 밖 지도 클릭 = 점프 유지, 원 안 단순 클릭(이동 없음)은 no-op. 지도 끌기·줌은 순수 탐색(재분석·API 호출 없음). img onload+재시도 패턴으로 지도 init 후 바인딩. 한때 "화면 중앙 고정 + 지도 드래그로 위치 잡기"(카카오T 픽업 방식)도 구현했으나, 이 지도는 위치 선택기가 아니라 히트맵·마커를 읽는 결과 화면이어서 "구경(팬·줌)"과 "분석 중심 변경"이 분리돼야 한다는 결론 — 팬·줌은 분석에 영향 없음(재분석·리마운트·API 호출 0), 클릭했을 때만 원+십자 핀(folium.Marker+DivIcon, CROSSHAIR_HTML)이 이동하고 재분석. 마커 클릭(팝업)은 last_object_clicked 비교로 제외, 처리한 클릭은 processed_click 세션 키로 중복 방지. 프리페치는 30m 격자 스냅 중심(FETCH_GRID_M)에 450m(FETCH_RADIUS_M)로 조회해 가까운 클릭 간 캐시 재사용, 분석 필터는 정확한 클릭 좌표 사용. 모바일 대응 시 "화면 중앙 고정" 방식 재검토 여지 있음.

Day 9 (서비스 피벗 + timeline/ 엔진 착수, 이번 세션에서 진행):
- 서비스를 "주류회사 영업사원용 영업 인텔리전스"로 재정의 (문서 최상단 "한 줄 정의"와 로드맵 A~D 참고). 핵심 산출물 = 음영지역 숨은 잠재 업소(목적지 지수).
- timeline/license_fetcher.py: LOCALDATA 인허가 CSV 로더 완성 — cp949/utf-8 자동 판별, 컬럼명 별칭 대응, EPSG:5174→WGS84 변환(pyproj 신규 의존성), 좌표·일자 결측/이상치 제거. ⚠️ localdata.go.kr이 curl 접속 불가(타임아웃)라 **자동 다운로드는 미구현** — 브라우저에서 월 1회 수동 다운로드해 data/에 두는 운영. data/는 gitignore.
- timeline/trend.py: filter_radius, yearly_trend(연도별 개업·폐업·순증), recent_openings(최근 N일 개업+경과일), site_turnover(같은 주소 폐업 이력 → 자리회전수), business_age(업력년). 합성 LOCALDATA CSV로 전 함수 검증 완료(좌표 왕복 오차 0).
- 아직: 실제 인허가 CSV 미확보(수동 다운로드 필요), app.py "변화" 탭 UI 연동 미착수.

Day 10 (전면 재개정 착수 — 계획 수립 + Phase 0·1 완료, 이번 세션에서 진행):
- **전면 재개정 계획 수립·승인** → `docs/REDESIGN_PLAN.md` (이후 진행 상황의 단일 출처 — 이 문서의 Phase 체크박스를 갱신하며 진행). 골자: 플러그인 아키텍처(Signal/AreaIndicator/Scorer/Provider 레지스트리), M0 구역 아웃룩(국면 매트릭스+지표 5개) + 업소 모델 8종(M1~M8), 하이브리드 진행(골격 최소 → 무료 모델 직행 → 구조 정리 → Naver → Places).
- **⚠️ LOCALDATA(localdata.go.kr) 2026-04-16 폐쇄 확인** → 공공데이터포털 통합. Day 9의 "수동 CSV 다운로드" 운영 전제가 무효화되고 **더 좋아짐**: 행안부 인허가 조회서비스 OpenAPI(`apis.data.go.kr/1741000/{general_restaurants|singing_bars|entertainment_bars}/info`)로 완전 자동화. 기존 `.env`의 SGIS_API_KEY(실체는 data.go.kr 공용키)로 3개 업종 즉시 호출 가능 확인. 스펙·실측치는 REDESIGN_PLAN.md "데이터 소스 현황" 참고.
- Phase 0 완료: 행안부 API 3종 + Naver 검색 API(블로그 postdate·지역 카테고리/좌표) 실호출 검증. `.env`에 NAVER_CLIENT_ID/SECRET 추가됨.
- Phase 1 완료: `core/`(schema·config·area) + `signals/`·`scorers/` 레지스트리 + `datasources/`(moi_api·build_index) + `tests/` 34개 그린. 강남구 단란주점 1,546행 실수집 검증. app.py는 **무수정** (병존 중 — Phase 3에서 분해).
- timeline/trend.py 5함수는 ROSTER 스키마와 컬럼 호환이라 그대로 재사용 (tests/test_trend.py가 회귀 감시).

▶ 다음 세션 시작점: `docs/REDESIGN_PLAN.md`의 Phase 체크박스 확인 → **Phase 2 (M0 구역 아웃룩)** — AreaIndicator 5개(net_momentum·vacancy_recovery·cohort_survival·liquor_shift·age_mix) + app.py "아웃룩" 탭. 데이터는 `data/cache/moi/{업종}/3220000.parquet` (강남구, gitignore라 PC마다 `python -m datasources.build_index --district 3220000`로 재수집).

아직 안 한 것: REDESIGN_PLAN.md Phase 2~6 전부 (M0 아웃룩 → 무료 모델 3종+우선순위 화면 → app.py 분해 → Naver 평판 축 → 확장 모델·증분 갱신 → Places).

Day 10까지의 변경분은 모두 커밋·푸시 완료. 새 PC에서는 clone/pull 후 `.env` 채우고(NAVER 키 2개 추가됨) `pip install -r requirements.txt`(pyarrow·pytest 추가, matplotlib 제거) 하면 이어서 작업 가능.
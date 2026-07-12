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

Day 11 (Phase 2b — 무료 업소 모델 + 변화·방문 우선순위 탭, 이번 세션에서 진행):
- signals 4개 추가: `survivor.py`(M2 생존자), `franchise.py`(M4 프랜차이즈 판별), `liquor_adjacency.py`(M5 주류 인접성), `recent_opening.py`(계획 외 — 신규 개업 골든타임, 180일 선형 감쇠. M8 "개업 직후 = 공급사 결정 시점" 전제의 무료 선반영).
- `scorers/weighted_sum.py`(가중합 베이스라인, 배지 없는 점수 금지 계약 준수) + `ui/changes_tab.py`("🔄 변화": 연도별 개폐업·최근 개업·자리회전) + `ui/ranking_tab.py`("🎯 방문 우선순위": 랭킹 표+근거 배지+지도, M0 국면 캡션 병기). app.py는 import·탭 배선만.
- **랭킹 정책 (사용자 피드백 2회 반영)**: 신규 개업(공급사 미확정)이 최우선, 생존 검증은 자리 평균 도달에서 포화(나이 단조성 제거)·가중 0.5, 프랜차이즈는 점수 미반영(체인 추정 정보 배지만 — "요즘 대부분 프랜차이즈라 제외는 과함"). 강남역 400m 실측: 1~12위 전부 2026년 개업, 13위부터 생존 검증 업소.
- 검증: pytest 56개 그린(`tests/test_business_signals.py` 신설 — 신호 계약·수치·가중치 0 배지 전용 동작). 강남구 3개 업종 53,278행 실수집 후 종단 확인.
- ⚠️ 트러블슈팅 기록: python.org 파이썬은 설치 후 `/Applications/Python 3.xx/Install Certificates.command`를 실행해야 urllib SSL이 동작한다(미실행 시 `CERTIFICATE_VERIFY_FAILED` — requests는 certifi 내장이라 멀쩡해서 원인을 놓치기 쉬움). moi_api가 urllib 사용.
- 잔여 알려진 한계: franchise 판별이 수집 자치단체 범위 기준이라 대형 체인 배지 누락 가능(전국 스캔은 Phase 5), 점수 미반영이라 실해는 없음.

Day 11 후반 (Phase 3 — 구조 정리, 같은 세션에서 진행):
- app.py(573줄) → 얇은 진입점(70줄). 분해 결과: `ui/state.py`(세션 키·UI 상수 단일 출처), `ui/sidebar.py`, `ui/map_view.py`, `ui/channels.py`(last_clicked·TURF_RADIUS 툴팁 채널 해석 집약), `ui/components/{charts,shop_table}.py`, `ui/pages/{explore,outlook,changes,ranking}.py`(기존 ui/*_tab.py는 git mv). 인라인 JS ~120줄은 `ui/map_interactions.js`로 격리(string.Template — %-format의 `%%` 함정 제거).
- 데이터 계층: `datasources/semas.py`(fetch_shops → ROSTER 어댑터) + `datasources/cache.py`(격자 스냅+TTL parquet 파일 캐시, st.cache_data 대체 — 프로세스 재시작을 넘어 유지). analyzer/presenter는 schema 상수로 전환(**by_category 컬럼명이 '상권업종소분류명'→'업종소'로 변경됨** — 이후 코드는 schema.CAT_S 사용). `collector/categories.py` 삭제, streamlit-folium `<0.28` 상한 고정.
- 검증: pytest 60개 그린(신규 `tests/test_semas.py` 골든 4개 포함). 실 API 골든 — main.py(Provider 경유)가 Day 1 콘솔 출력과 수치 완전 동일. 강남역 파일 캐시 5,840행/캐시 히트 0.02s. 앱 기동 에러 없음.
- 함정 기록: 전-NaT datetime 컬럼은 s 단위로 추론돼 parquet 왕복 시 ms로 바뀜 → semas 어댑터에서 ns 명시. AREA_M2도 float 명시(왕복 후 object None 방지).

Day 11 마무리 (Phase 4 — Naver 평판 축, 같은 세션에서 진행. Phase 3 브라우저 스모크는 사용자 확인 완료):
- `matching/normalize.py`(상호 정규화 단일 출처 — franchise의 임시 버전 이관·확장, 과제거 시 원형 유지) + `matching/matcher.py`(30m 격자 블로킹, rapidfuzz×거리 감쇠, 임계 0.82 보수적, 1:1 greedy — 통합 업소 테이블의 기초, UI 실사용은 추후).
- `datasources/naver.py`: 블로그 검색 + 주소 토큰 필수(동>로/길>구 — 동명 오매칭 방어) + 7일 파일 캐시 + 레이트 슬립. signals: `buzz_momentum.py`(M8 — 골든타임만 조회, 쿼터 방어를 테스트로 강제), `review_momentum.py`(R=log(1+블로그6개월)/업력) → `scorers/destination_index.py`(M1 Naver판).
- **M1 입지 기대치 E**: SGIS 키 부재로 원안(유동 십분위) 대신 **업소 밀집도 십분위(300m) 프록시**. 코호트 폴백 = (업태×십분위)→십분위→전체 — 업태 평균 폴백은 음영지역 외톨이를 번화가 평균과 비교해 눌러버리는 결함이 테스트로 확인돼 배제.
- ranking 탭: 랭킹 기준 radio(가중합↔목적지 지수), Naver 키 있으면 평판 신호 자동 활성. pytest 71개 그린.
- 강남역 400m 실측: 453곳 전수 조회(캐시 674건), 블로그 관측 421곳. **목적지 지수 6위 '지안식당' = 밀집도 1/10 구간에서 블로그 100건 — 음영지역 숨은 잠재 업소 가설의 첫 실물 사례.** 버즈: 개업 98일차 블로그 100건(샐러링) 등 9곳.
- 이 PC `.env`에 NAVER 키 2개 추가됨(회사 PC와 별개로 재입력 필요했음 — .env는 gitignore).

Day 12 (Phase 5 마무리 — M7 야간 지수 + M4 전국 스캔, 이번 세션에서 진행. M3/M6은 회사 PC에서 선행):
- **M4 전국 스캔**: 영업중 필터(SALS_STTS_CD=01)로 호출량 24,600→7,134회 절감(전국 영업중 71.3만 건) — 3일 분할이 하루 안으로. `datasources/national_names.py`: 페이지 단위 정규화 상호만 집계(71만 행 메모리 미적재), 200페이지 체크포인트로 중단·재개 가능(`python -m datasources.national_names` 재실행 = 이어서). franchise 신호는 전국 카운트(임계 5) 우선, 없으면 수집범위 폴백(임계 3). ⚠️ 전국 무필터 조회는 API가 페이지당 ~2.5s로 느려 **전체 약 5시간** — nohup으로 실행.
- **M7 야간 상권 지수 v1** (`signals/night_index.py` + `datasources/seoul.py` + config.seoul_key): 주변 300m 명시적 주류 업태(affinity≥2) 비중 백분위 × 행정동 심야(23~04시) 생활인구 비율. 좌표→행정동 = VWorld 리버스 지오코딩(level4AC 앞 8자리, 강남역→역삼1동 11680640 실검증). 생활인구 게시 지연 대응(14일 전부터 탐색). 서울 밖 우아한 강등. **함정 기록: liquor_affinity는 한식도 1점(반주)이라 ≥1로 세면 전부 주류친화 — 야간 지수는 ≥2(호프·주점급)만 센다.**
- `.env`에 SEOUL_OPEN_DATA_KEY 추가됨(이 PC). moi_api에 fetch_page(단일 페이지) 분리.
- 검증: pytest 85개 그린. 강남역 실측 — 야간 지수 453행/배지 92곳(역삼1동 심야 56%), M3 배지 185곳·M6 배지 7곳 스팟체크 리스트 생성(육안 확인 잔여).

Day 12 후반 (Phase 6 — Places 완전판, 같은 세션에서 진행):
- **요금 실측** (2025-03 개편 후): Text Search IDs Only 무제한 무료 / Details Pro(businessStatus) 월 5,000 / Details **Enterprise(평점·리뷰수·영업시간) 월 1,000**. 평점·리뷰수도 영업시간과 같은 Enterprise — 필드를 빼도 등급 안 내려감.
- `datasources/places_quota.py`: 월별 원장 — **무료 한도의 90%에서 하드 스톱**(QuotaExceeded, HTTP 발생 자체 차단), 월 자동 리셋. 사용자 요구: 무료 한도 초과 호출 금지.
- `datasources/places.py`: 원장 경유 강제 + 30일 캐시(히트는 쿼터 0). **등급 분리(사용자 결정)**: find_place_id(무료) / business_status(Pro — 폐업검증 넓게) / place_snapshot(Enterprise — 최상위만). 파서: is_late_night(자정 롤오버·24h), snapshot_badges, status_badge.
- 랭킹 탭 2패스: 상위 10 평판 스냅샷 + 11~30 폐업 검증, QuotaExceeded는 등급별 우아한 생략. `.env`에 GOOGLE_PLACES_API_KEY 추가됨(Google Cloud Console에서 발급 — AI Studio 아님 주의).
- **강남역 실측**: 상위 10곳 전부 구글 평점 배지. **3위 스시오사카 = 인허가 영업중 + 구글 폐업 → M2 헛걸음 제거 첫 실전 적중.** 지안식당 구글 5.0/82(M1 교차 확인), 다운타우너 심야영업 배지. 쿼터 무료31/Pro20/Ent10. pytest 99개 그린.

Day 13 (전국 스캔 CSV 전환 + 영업사원 관점 UI 3탭 전면 개편, 이번 세션에서 진행):
- **전국 스캔 CSV 전환**: API 전국 스캔(6,700+ 호출·5시간)이 네트워크 끊김으로 3번 죽음(최대 41%) → 공공데이터포털 전국 인허가 CSV(LOCALDATA 형식 cp949, `data/permit_all.csv` 228만 행)를 `scan_from_csv()`로 30초 집계로 대체(영업중 676,390건 → 고유 상호 478,434개). 출력은 API 경로와 동일한 `national_name_counts.parquet`이라 franchise 무수정. 전국 빈도는 거의 정적이라 몇 달 1회 CSV 재수집이면 충분. API `scan()`은 폴백 유지(재시도 30회+백오프 상수화). 대형 체인 정확(김밥천국 695·투다리 443), 강남 453곳 중 체인 배지 54곳. 한계: 써브웨이·스타벅스처럼 지점명에 지역 붙는 체인 미검출(normalize 한계, 점수 미반영이라 실해 작음).
- **타이틀 → "Sales Radar"** (page_title + 사이드바). 구 "공공API기반의 상권분석"은 창업자용 상권분석 시절 잔재.
- **UI 5탭 → 3탭 전면 개편 (영업사원 관점)**: 지도 / 📈 구역 동향 / 🎯 방문 우선순위. 창업자용 잔재(업종 구성 탭, 업종 다중필터, 밀집도 히트맵) 제거. 전 화면이 MOI 인허가 데이터 위에서 동작(SEMAS는 provider로만 잔존, UI 미사용 — 수집 안 된 지역은 지도도 빔).
  - **지도**: SEMAS→MOI 전환. 주류 가능 업소(liquor_affinity≥1, 토글로 ≥2 주류중심만)를 신규🟢(최근 90일)·폐업🔴(최근 180일)·영업⚪ 색으로. 업종 다중필터 삭제. (함정 수정: 최초 구현이 '영업중 아니면 전부 폐업'이라 역대 폐업 1,015곳이 다 찍힘 → 최근 폐업만 남기고 오래전 폐업은 제외.)
  - **구역 동향** (구 아웃룩+변화 통합): 국면 차트 + 핵심지표 3개(순증 모멘텀·주류친화 전환율·신규 생존율, age_mix 제외) + 최근 신규🟢/폐업🔴 리스트. **반경 정책: 지표·국면은 선택 반경 우선, 표본<30이면 담당구역 800m 자동 확대(core.area.adaptive_area)하고 그 사실 명시**. 최근 변화 리스트는 선택 반경 기준. 주류친화 전환율 expander에 포함 업태 목록 노출(모호하다는 피드백 반영).
  - **방문 우선순위**: 방문 리스트 CSV 내보내기 흡수(구 업종구성 탭에 있던 것).
  - 신호등/배지: `ui/theme.py`(전역 CSS — 가로스크롤 방지·카드·배지칩), `ui/components/badges.py`(퍼센타일·신선도·쿼터 신호등, 배지칩), `ui/components/csv_export.py`(수식주입 방지). 삭제: `ui/pages/changes.py`, `ui/components/charts.py`, `ui/components/shop_table.py`.
- 함수 시그니처 변경: `render_outlook(cx,cy,radius)`, `render_map_tab(roster,cx,cy,radius)`. `trend.recent_closings()` 신설.
- 검증: pytest 105개 그린(신규 test_explore_map·adaptive_area·recent_closings·scan_from_csv 포함). 강남역 400m 실측 — 지도 영업402·신규8·폐업17, 앱 기동 에러 없음.

Day 14 (정지작업 — 화면 지연 실행 + 계산 캐싱, 이번 세션에서 진행. 챗봇·피드백 기능의 선행 조건):
- **로드맵 확장 결정 (사용자)**: ① 모든 화면에 챗봇(제시 데이터·평가 근거에 대한 보충질문) ② 영업사원 맞아요/틀려요 피드백 수집 → 지표 조정 데이터로 활용. 합의된 순서: 1 정지작업(이번) → 2 피드백 수집(스냅샷 스키마 + 사유 분기 버튼: 사실 정정/방문 가치/이미 거래처) → 3 챗봇 MVP(현재 화면 결과 컨텍스트 스터핑 + 판단 원칙 가드레일) → 4 배지별 적중률 대시보드 → 수동 가중 조정 → 표본 충분 시 학습 스코어러(가중합이 선형이라 로지스틱 회귀 계수로 대체 가능).
- **st.tabs → st.segmented_control 분기** (app.py): st.tabs는 보이지 않는 탭의 with 블록도 매 rerun 실행 — 지도만 보는 사용자도 Naver 전수조회·Places 쿼터를 소모하던 문제 제거. 이제 선택된 화면만 실행된다. 컨트롤 해제(재클릭) 시 지도로 폴백. streamlit>=1.40 하한 상향.
- **ui/data.py 신설**: 공용 캐시 로더 load_roster() — app.py·outlook·ranking에 3벌 복제돼 있던 _load_roster 통합(st.cache_data는 함수 단위 캐시라 3벌 = 같은 명부 메모리 3번).
- **계산 캐싱** (모두 st.cache_data, 명부는 DataFrame 해싱을 피해 내부 로드, 키 = 파티션 목록+좌표+반경+날짜): ranking `_cached_signal_results`(신호 전체 — O(n²) 이웃 루프 3개·Naver 캐시 순회가 rerun마다 반복되던 것), `_google_verification`(DataFrame→튜플 인자로 바꿔 캐시화), outlook `_cached_indicator_results`(grid_percentile이 가장 무거움), explore `_cached_display`. 실측: 랭킹 첫 계산 후 스코어러 radio 전환이 ~40초 → 수 초.
- **버그 수정 (검증 중 발견, 기존 버그)**: 구역 국면 미러 차트에서 개업(녹색) 막대가 아예 렌더되지 않던 문제 — **pandas melt는 id_vars에 있는 컬럼을 value_vars에서 조용히 제거한다** ("개업"이 양쪽에 있었음). 개업표시 컬럼을 분리해 해결. SVG 검사로 확진(폐업 막대만 존재, 녹색은 범례 심볼뿐).
- **watchdog 설치+requirements 추가**: 폴링 파일 감시가 모듈(비-app.py) 변경 리로드를 놓쳐 구 코드가 계속 서빙됨 — 세션 중 2회 발목. ⚠️ **이 변경 적용에는 기존 실행 중인 streamlit 서버 재시작 필요.**
- 시그니처 변경: `render_map_tab(cx, cy, radius)` — roster 인자 제거(내부에서 캐시 로드). `_render_phase_matrix(local)`, `_render_indicator_cards(results_by_id)`.
- 검증: pytest 105 그린. 브라우저 — 3화면 전환, 지도(슬라이더·토글·마커·원), 구역 동향(국면 차트 개업+폐업 완전 렌더·지표 카드 3장·최근 변화), 방문 우선순위(목적지 지수/가중합 전환 캐시 히트, Places 쿼터 신호등) 확인.

Day 14 후반 (목적지 지수 배지에 기대치 근거 병기 — 핵심 수치의 신뢰 문제, 같은 세션에서 진행):
- **"기대치의 N배" 배지에 근거 병기** (scorers/destination_index.py): E가 어느 단계에서 왔는지를 업소별로 추적(`E근거`/`E표본`/`E바닥`)해 배지에 명시 — ① 코호트 "기대치 = 같은 구간 한식 10곳 평균" ② 구간 폴백 "같은 구간 전체 34곳 평균 (동일 업태 표본 5곳 미만)" ③ 구역 폴백 ④ 바닥값 발동 시 "비교군 평균이 바닥값(0.05) 미만이라 바닥값으로 나눔 — 배수는 하한값" (바닥값은 E를 올리므로 표시 배수는 실제 코호트 대비보다 작다 = 하한). 스코어러 description에도 폴백 체인 명시.
- **테스트 픽스처 결함 발견·수정** (tests/test_reputation.py): 목적지 지수 랭킹 테스트의 "골목"이 번화가에서 246m — 밀집도 반경(300m) 안이라 **전부 한 코호트로 묶여 두 밀집 코호트가 애초에 분리되지 않았고**, 순위 검증은 동점(DI 동일) 정렬 안정성 덕에 우연히 통과하고 있었음. 골목을 350m로 이동해 시나리오를 의도대로 복원 + 코호트 근거 배지 검증 추가 + 바닥값 배지 테스트 신설.
- 검증: pytest 106 그린. 강남역 400m 실측 — 상위 30곳 배지에 코호트/구간 폴백 근거가 실제 병기됨(1위 광장포차 "같은 구간 전체 34곳 평균", 8위 강남막국수 "같은 구간 한식 10곳 평균").

Day 14 마무리 (제3 스코어러 '알려진 스타' — 규모 축, 같은 세션에서 진행):
- **기준 논의(사용자 제안 '증분' → 합의)**: 누적 절대량은 업력·과거 마케팅의 함수라 부적합(동의)하나, 증분을 판정 기준으로 쓰면 ① 안정 스타(증분 0)가 빠지고 ② 기존 모멘텀 지표들과 역할이 겹치고 ③ API 100건 캡 때문에 상위권일수록 직전 창이 잘려 가짜 급증이 남. 합의안: **판정 = 현재 게재 속도(월 환산, 업력으로 나누지 않음 — 리뷰 모멘텀과의 결정적 차이)의 구역 내 백분위 상위 20%, 증감(최근 90일 vs 직전 90일)은 배지의 변곡 정보**(급증=물량 확대 국면, 급감=관계 흔들리는 접점 — 표기는 관측 사실만).
- `datasources/naver.py: blog_post_dates()` 신설 — 같은 쿼리·같은 파일 캐시라 **추가 쿼터 0**. `signals/star_level.py`: 캡 대응 이중 레짐(100건이 180일 창에 다 안 들어오면 날짜 범위 기준 속도 + 증감 생략 / 아니면 창 건수 기준 + prior≥5일 때만 증감 %). `scorers/known_star.py`: 스타 배지 업소만 랭킹(배지 없는 점수 금지와 일치). weighted_sum에는 가중 0(배지만 — 타이밍 랭킹에 규모 축이 섞이지 않게).
- **함정 재발**: 배지 조립에서 `if trend is not None:` — None이 DataFrame float 컬럼에서 NaN이 되어 실데이터에서 "+nan%" 노출 (weighted_sum에 기록된 것과 동일 함정, 테스트는 전 행 None=object dtype이라 우연히 통과). `pd.notna()`로 수정 + 혼재 dtype 회귀 테스트 추가. **또한 신호 코드 수정은 `_cached_signal_results` 캐시(TTL 10분)에 안 잡힌다 — 신호/스코어러 수정 후에는 서버 재시작(또는 캐시 클리어)해야 반영.**
- 검증: pytest 108 그린. 강남역 300m 실측 — 신호 276행, 스타 배지 56곳, 랭킹 라디오 3개(목적지 지수/알려진 스타/가중합) 동작. 상위 = 월 176~333건 페이스 대형 계정(써브웨이·리춘시장 등, 전부 캡 구간이라 증감 생략), 증감 표기는 캡 미달 2곳("-18%", "-37%" 감소 — 급감 접점 사례).

Day 15 (지표 개선 4건 — 코드 리뷰 지적 잔여분, 이번 세션에서 진행):
- **국면 라벨 개선**: ① 완충대 — 직전 대비 ±10%(PHASE_BUFFER) 안쪽 증감은 '변화 없음' 판정(개업 12→13이 '확장'이 되던 과민 제거). ② `outlook.current_phase()` 신설 — 헤드라인 국면을 달력 연도(최대 18개월 지연) 대신 **최근 12개월 vs 직전 12개월 이동창**으로 판정, 구역 동향 헤더·방문 우선순위 캡션 모두 교체(연도 차트는 유지, 연도별 이모지도 완충대 적용). 강남역 실측: 개업 18 vs 19(완충대 안)·폐업 28 vs 23(+22%) → 수축.
- **생존자 지수 자리평균 축소추정**: 폐업 1건짜리 자리의 "0.2년의 10배" 같은 배지 방지 — 자리평균 = (표본수×자리관측 + 지역평균)/(표본수+1). DETAIL에 보정 명시.
- **목적지 지수 설명에 체험단 한계 1줄** 추가 (블로그 수는 체험단·광고로 부풀 수 있음).
- **휴게음식점 인입 준비 완료 (수집만 대기)**: 엔드포인트 = `rest_cafes` (data.go.kr '행정안전부_식품_휴게음식점 조회서비스' data/15154921 — 페이지가 JS 뒤에 숨겨 브라우저로 확인). ⚠️ **같은 키로 403 — 이 API는 data.go.kr 로그인 후 별도 활용신청 필요** (기존 3종은 즉시 200이었던 것과 다름). 코드는 전부 선반영: SERVICES 추가, normalize가 CAT_L=업종명 채움(기존 파티션은 None, 재수집 시 채워짐), `liquor_affinity`/`is_liquor_friendly`에 cat_l 인자(휴게음식점 = 무조건 0, 주류 판매 불가 인허가) + 호출부 5곳(지도·야간지수·주류인접·전환율·전환벡터) 전달, **방문 우선순위 랭킹에서 affinity 0 업소 제외**(지도와 같은 기준, "주류 판매 불가 업소 N곳 제외" 캡션 — 강남역 400m 실측 23곳 제외, 기존 일반음식점 파티션의 분식·카페 업태 포함). 전국 스캔은 SCAN_CATEGORIES(기존 3종)로 분리(휴게는 랭킹 제외 대상이라 체인 판별 실익 낮음). **활용신청 승인 후**: `python -m datasources.build_index --district 3220000 --category 휴게음식점` 한 번이면 인입 완료.
- **지위승계(사장 교체) 조사 결론**: ① 행안부 API 응답에 승계·대표자 필드 없음(전 필드 덤프 확인) — 직접 관측 불가. ② `LAST_MDFCN_PNT`(최종수정시점) 필드는 있으나 **cond 필터가 조건 조합에서 조용히 무시됨**(실측: GTE 2026-06-12 필터에 5/11 수정 건 통과) — API 필터 기반 조회 신뢰 불가. ③ 실행 가능 경로 = 증분 갱신(DAT_UPDT_PNT, build_index --update가 이미 사용) 시 기존 파티션과 diff → "기존 영업중 업소에 변경 발생"은 정확히 감지되나 원인(승계/면적변경/행정처분) 구분 불가 — 약한 프록시로만 가능. ④ 식약처 전용 API 여부는 식품안전나라 시스템 점검으로 미확정(잔여 과제). scripts/verify_mfds_api.py는 예비 폴백으로 유지.
- 검증: pytest 113 그린(국면 완충대·current_phase·휴게 affinity·생존자 축소추정 테스트 추가). 브라우저 실측 — 구역 동향 헤드라인 "최근 12개월 기준 📉 수축"(판정 수치 병기), 랭킹 "주류 판매 불가 업소 23곳 제외" 캡션.

▶ 다음 세션 시작점: ① (사용자 액션) data.go.kr에서 '행정안전부_식품_휴게음식점 조회서비스' 활용신청 → `python -m datasources.build_index --district 3220000 --category 휴게음식점` 실행 ② **2단계 피드백 수집** — 랭킹 카드 👍방문가치 높았음/👎없었음 2버튼 + 업소 속성 채널 분리(⋯ 메뉴: 폐업했어요/우리 거래처예요 — 라벨 오염 방지 설계 확정), 노출 로그(상위 30 스냅샷)와 피드백 시점 신호값 벡터 저장. 이후 3단계 챗봇 MVP.

잔여 소과제: M7 v1.1(지하철 심야 승하차), Google Cloud 콘솔 키 일일 상한 설정, 매칭 임계 튜닝, 써브웨이류 체인 판별(지명 사전), M1 완전판 점수 결합(유료 확장 결정 후). 지표 개선 검토 대상(Day 14 코드 리뷰 지적, 기대치 근거 병기는 완료): 국면 라벨 이동창+완충대 전환, 휴게음식점 파티션 수집, 지위승계(사장 교체) 신호 조사.

Day 13까지의 변경분은 모두 커밋·푸시 완료(스캔·캐시·CSV 원본은 data/라 gitignore). 새 PC에서는 clone/pull 후 `.env` 채우고(키 6개: data.go.kr·VWorld·NAVER 2·SEOUL·PLACES) `pip install -r requirements.txt` + 전국 CSV는 `python -m datasources.national_names --csv data/permit_all.csv`, 구역 데이터는 `python -m datasources.build_index --district 3220000` 하면 이어서 작업 가능.
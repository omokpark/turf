한 줄 정의: 특정 위치와 반경을 넣으면, 그 안의 음식점 경쟁 지형을 업종별 통계로 보여주는 도구.

판단(들어갈까 / 버틸까 / 바꿀까)은 하지 않는다. 지형만 그린다.


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
├── timeline/             ← 아직 착수 안 함 (Day 1~6은 스냅샷 쪽만 진행)
│   ├── license_fetcher.py ← 인허가 데이터 다운로드·로드
│   └── trend.py           ← 개폐업 시계열 집계
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

아직 안 한 것:
- timeline/ 모듈(개폐업 시계열) 전혀 착수 안 함 — license_fetcher.py, trend.py는 CLAUDE.md 계획에만 존재.
- GitHub Actions 등 배포/자동화 (5장 "실행 환경" 항목의 "안정화 후" 단계).

⚠️ 이 세션에서 만든 app.py/analyzer/terrain.py 변경사항과 collector/categories.py, collector/geocoder.py 파일은 아직 git commit이 안 되어 있을 수 있다. 새 PC에서 이어서 하기 전에 `git status`로 확인하고 커밋·푸시부터 할 것.
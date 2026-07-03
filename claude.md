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
│   └── shop_fetcher.py   ← 상가정보 API 호출
│
├── analyzer/
│   └── terrain.py        ← 업종별 집계·통계
│
├── presenter/
│   └── report.py         ← 경쟁 지형 문구 생성
│
├── timeline/
│   ├── license_fetcher.py ← 인허가 데이터 다운로드·로드
│   └── trend.py           ← 개폐업 시계열 집계
│
├── app.py                ← Streamlit 지도 UI (Day 3)
└── main.py               ← 콘솔 실행 진입점 (Day 1~2)


2. 기술 스택

항목선택언어Python 3.11+API (스냅샷)소상공인시장진흥공단 상가(상권)정보 API (data.go.kr)API (시계열)행정안전부 일반음식점 인허가 데이터 (data.go.kr, CSV 파일)데이터 처리pandas시각화matplotlib (Day 4)지도 UIStreamlit (Day 3)실행 환경로컬 → GitHub Actions (안정화 후)보안.env + .gitignore


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
matplotlib>=3.8      # Day 4


6. 보안 체크리스트


API 키: 코드에 직접 넣지 않는다. 반드시 .env로 분리.
호출량: 반경이 넓으면 페이지 단위로 결과가 나뉜다. 테스트는 반경 300~500m로 시작.
개인정보: 상호·주소는 공개 사업장 정보. 화면 출력·개인 사용은 안전.



7. 개발 금지 패턴


판단 문구 삽입 금지: '여기는 창업하기 좋습니다' 같은 추천·예측 문구는 넣지 않는다.
UI 먼저 금지: 엔진(collector → analyzer → presenter)이 먼저 완성돼야 한다. 지도는 Day 3.
반경 무제한 금지: 첫 테스트는 500m 이하. API 호출 한도 소진 방지.
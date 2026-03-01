# 🚀 AutoTradingServer UI 개발 일지 (feature/ui-development)

이 문서는 새롭게 추가된 대시보드 UI(`feature/ui-development` 브랜치)의 현재까지 진행 상황과 향후 작업 방향을 기록합니다.

## 📌 현재까지 작업 완료 내용 (Last Done)
1. **정적 파일 구조 설정**
   * `/static` 디렉토리 생성
   * FastAPI 라우터(`/`)에 `StaticFiles` 및 `FileResponse` 마운트 추가하여 프론트엔드 자원이 서빙되도록 구현 (`webhook_server.py`)

2. **프론트엔드 퍼블리싱 (UI 뼈대 & 스타일링)** 
   * **`index.html`**: 시맨틱 태그 구조 및 Hero Metrics(잔고, 승률 등), Current Position 패널, Chart 영역, History Table 레이아웃 구축.
   * **`style.css`**: 현대적이고 트렌디한 **다크 모드 + 글래스모피즘(Glassmorphism)** 테마 적용.
      * CSS Variables 기반의 색상 관리 및 형광(Neon) 포인트 컬러로 지표 가독성 극대화.
      * 호버링(Hover) 및 컴포넌트 등장 애니메이션 등 부드러운 시각적 효과 포함.
   * **`app.js`**: 프론트엔드가 동작하는지 확인할 수 있도록 **가짜(Mock) 데이터**를 바인딩하고 타이머 기반 애니메이션 테스트 코드 구축.

## 🔜 향후 진행할 작업 (To-Do List)
1. **백엔드(FastAPI) 상태 조회 API 연동 (`/api/status` 등)**
   * UI가 호출할 수 있는 전용 엔드포인트 생성.
   * 임시 데이터로 보여주던 잔고(`prev_balance`), 승/패 카운트(`win`, `lose`), 실제 포지션 상태(`trading.py` 호출) 및 실시간 최근 웹훅 메시지 내역을 JSON으로 반환하도록 작업.
2. **프론트엔드 실시간 폴링 구조(`fetch`) 완성**
   * `app.js`의 `setTimeout` 가짜 데이터 주입 코드를 삭제하고, 실제 `/api/status` 경로를 `setInterval` 등의 방법으로 실시간 갱신 구조로 변경.
3. **최적화 및 데이터베이스(스프레드시트 등) 연동 대비**
   * 추후 DB 담당자가 만들어줄 구조를 수용하기 쉽게 프론트-백 간 비동기 인터페이스(Mocking API) 구조 다듬기.

> **현재 저장소 브랜치**: `feature/ui-development`

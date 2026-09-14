# 주간 진행 보고 (Week 2)

- **제목**: CS40008 전산학 프로젝트 — 웹취약점 탐지 AI Agent
- **기간**: Week 2
- **환경**: Windows 네이티브, Python 3.11, Selenium + Chrome(CDP), Ollama(qwen2.5:7b)

## 완료
  - XSS/SQLi/IDOR 시나리오·성공 판정 기준 정리 (`docs/vuln-scenarios.md`)
  - 최소 Agent 루프 (LLM이 도구 호출 → 결과 판단) — 로컬 모델 qwen2.5:7b 실동작 검증
  - Selenium 접속/로그인/쿠키 유지 예제
  - `PageExplorer`: 동일 호스트 링크/폼/입력 탐색, 중복 방문 방지, 깊이 제어
  - `NetworkCollector`: CDP 로그에서 API 경로·파라미터·JS 리소스 수집
  - 웹 환경 프로파일 결합(`WebProfile`): 두 결과를 합쳐 **입력 지점(공격 표면)** 목록 도출
    - `query / form / api_param / path_id` 로 정규화, IDOR 후보 경로 식별자 자동 표기

## 검증
- the-internet.herokuapp.com: 크롤 25페이지 → 폼 입력 지점 추출
- httpbin.org: XHR API(`/spec.json`) 및 POST 본문 파라미터 캡처

## 다음
- 오케스트레이션 루프: LLM이 InputPoint를 읽어 탐지 도구를 선택, 상태 관리·종료 조건(호출/시간 상한)
- 진짜 정찰 도구(`explore_site`)를 Agent 루프에 연결 (현재는 도구·LLM 각각만 동작)

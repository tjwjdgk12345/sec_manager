# 웹취약점 탐지 AI Agent (CS40008)

웹사이트를 대상으로 AI Agent가 화면·요청 경로를 탐색해 **XSS / SQLi / IDOR** 후보를 찾고,
허용된 실습 환경에서 PoC로 재현·검증한 뒤 보고서로 정리하는 자동화 파이프라인.

> 자세한 범위/주차 계획은 [PROJECT_PLAN.md](PROJECT_PLAN.md), 취약점 판단 기준은 [docs/vuln-scenarios.md](docs/vuln-scenarios.md) 참고.
> **모든 자동 요청/브라우저 조작은 허용된 테스트 사이트에만 수행한다.**

## 요구 사항
- Windows 네이티브, Python 3.11+
- Google Chrome (설치되어 있어야 함 — ChromeDriver는 Selenium Manager가 자동 관리)
- (선택) 도구 호출 지원 로컬 LLM: [Ollama](https://ollama.com)

## 설치
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ollama 준비 (Agent용 로컬 LLM)
```bash
# 1) https://ollama.com 에서 설치 후
ollama pull qwen2.5:7b      # 도구 호출(tool calling) 지원 모델
```
Ollama 없이도 개발/테스트가 가능하도록 `MockClient`(가짜 LLM)를 제공한다.

## 실행 예제 (1주차)
```bash
# 최소 Agent 루프 — 모델 없이 (Mock)
python examples/minimal_agent_loop.py

# 최소 Agent 루프 — Ollama 로컬 모델
python examples/minimal_agent_loop.py --backend ollama --model qwen2.5:7b

# Selenium 접속/로그인/쿠키 데모 (공개 연습 사이트)
python examples/selenium_login_demo.py --headless
```

## 디렉터리 구조
```
src/
  llm/client.py       LLM 추상화 (OllamaClient / MockClient) + 도구 호출
  agent/tools.py      도구 레지스트리 + JSON Schema 스키마
  agent/loop.py       최소 오케스트레이션 루프 (도구 호출 상한 포함)
  browser/session.py  Selenium 세션: 접속/로그인/쿠키 저장·복원, CDP 로그 활성화
examples/             1주차 실행 데모
docs/                 취약점 시나리오·판단 기준
reports/              주간 보고서 (week-XX-report.md)
```

## 진행 상황 (1주차)
- [x] XSS/SQLi/IDOR 시나리오·판단 기준 정리 (`docs/vuln-scenarios.md`)
- [x] 최소 Agent 루프 (LLM이 도구 1개 호출 → 결과 되먹임)
- [x] Selenium 접속/로그인/쿠키 유지 예제
- [ ] Ollama 로컬 모델로 실 루프 검증 (모델 pull 후)

# 멘토링 시연 가이드 (Week 1–3)

> 금요일 시연용. "수집 → 분석" 파이프라인이 실제로 도는 걸 순서대로 보여준다.
> 전체 처리 흐름(수집 → 분석 → PoC → 검증 → 보고서) 중 **수집·분석 기반**까지 완료.

## 0. 사전 준비 (미팅 전에 미리)
- 인터넷 연결 확인 (데모가 the-internet.herokuapp.com / httpbin.org 에 접속)
- 한 번 미리 돌려서 ChromeDriver 캐시·정상 동작 확인 (라이브에서 첫 실행이 느릴 수 있음)
- 가상환경 활성화:
  ```bash
  .venv\Scripts\activate
  ```
- 시연 팁: `--headless` 를 **빼면** 크롬 창이 실제로 뜨고 움직이는 걸 보여줄 수 있음 (임팩트↑).
  네트워크가 불안하면 `--headless` 로 안정성 우선.

---

## 1. 큰 그림 먼저 (말로 설명, 30초)
- 목표: AI Agent가 웹사이트를 탐색해 **XSS/SQLi/IDOR 후보**를 찾고 PoC로 검증하는 자동화 파이프라인
- 대상: OWASP Juice Shop (수업 제공 예정) → 그 전까지 **대상-불특정 컴포넌트를 범용 사이트로 선행 개발**
- 오늘 보여줄 범위: **① Agent 도구 호출 구조 ② 브라우저 자동화 ③ 페이지·네트워크 정보 수집 ④ 통합 프로파일(공격 표면 도출)**

---

## 2. 데모 A — 최소 Agent 루프 (Week 1)
"LLM이 도구를 골라 호출하고, 결과를 근거로 판단하는 최소 구조"

```bash
python examples/minimal_agent_loop.py
```
**보여줄 것 / 말할 것**
- 목표 → `reflect_probe` 도구 **호출**(payload 전달) → 결과 되먹임 → "반사 확인됨 → XSS 후보" 결론
- LLM을 갈아끼울 수 있게 추상화(OllamaClient/MockClient)해 둠 — Mock 은 모델 없이 루프 구조 검증용
- **실제 로컬 모델(하이라이트)**: 경량 모델이 스스로 도구를 고르고 판단:
  ```bash
  python examples/minimal_agent_loop.py --backend ollama --model qwen2.5:7b
  ```
  → qwen2.5:7b 가 목표 문장에서 payload 를 추출해 `reflect_probe` 호출 후 자연어로 결론
  → 계획서 제약(경량 로컬 모델) 충족. 첫 실행은 모델 로딩으로 느리니 **미팅 전에 한 번 워밍업** 권장

---

## 3. 데모 B — Selenium 접속/로그인/쿠키 (Week 1)
"브라우저를 코드로 조종 — 로그인하고 세션을 유지"

```bash
python examples/selenium_login_demo.py
```
**보여줄 것 / 말할 것**
- 접속 → 아이디/비번 입력 → 로그인 성공 → 쿠키 저장 → 새 세션에서 복원
- `screenshots/after_login.png` 캡처가 증거로 남음
- 왜 Selenium? → JS로 렌더링되는 최신 사이트(특히 Juice Shop = Angular SPA)의 **최종 화면**을 봐야 하고, 실제 요청을 재현해야 하므로

---

## 4. 데모 C — PageExplorer (Week 2-3) ★핵심
"같은 호스트를 돌며 링크·폼·입력 필드를 자동 수집"

```bash
python examples/pageexplorer_demo.py --depth 1 --max-pages 12
```
**보여줄 것 / 말할 것**
- BFS로 페이지를 돌며 각 페이지의 폼/입력/링크 추출, **중복 방문 방지 + 깊이 상한**
- 로그인 폼 하나만 콕 집어 보여주기 (입력 필드 이름·타입까지 추출):
  ```bash
  python examples/pageexplorer_demo.py --url https://the-internet.herokuapp.com/login --depth 0 --max-pages 1
  ```
  → `[POST] /authenticate (username:text, password:password)`
- Juice Shop 대비: `--spa` 옵션으로 Angular 해시 라우팅(#/route) 대응 준비됨

---

## 5. 데모 D — NetworkCollector (Week 2-3) ★핵심
"CDP 로그에서 API 경로·파라미터·JS 리소스를 수집"

```bash
python examples/networkcollector_demo.py
```
**보여줄 것 / 말할 것**
- 진짜 브라우저의 네트워크 로그(CDP)에서 요청/응답 메타데이터 수집
- httpbin 첫 화면(Swagger UI)이 쏘는 **XHR API `[GET] /spec.json` 캡처**
- 요청 본문 파라미터(JSON/form)까지 파싱 → 어떤 입력이 서버로 가는지 파악
- 스코프 호스트 필터로 서드파티(폰트·애널리틱스) 노이즈 제거

---

## 6. 데모 E — 웹 환경 프로파일 결합 (Week 2-3 마무리) ★하이라이트
"페이지 구조 + 네트워크를 합쳐, 탐지기가 공격할 **입력 지점 목록**을 도출"

```bash
python examples/webprofile_demo.py --depth 1 --max-pages 25
```
**보여줄 것 / 말할 것**
- 한 번의 정찰로 크롤 + 네트워크 수집 + 결합을 자동 수행 (`ReconRunner`)
- 결과: **InputPoint(공격 표면)** 목록 — `query / form / api_param / path_id` 로 정규화
  - 예: `[form][POST] /authenticate param=password` , `[path_id][GET] /rest/user/{id}`
- 각 입력 지점에 **우선 시도할 취약점 힌트**(xss/sqli/idor) 부여 → 다음 단계(탐지기 선택)로 바로 연결
- `path_id` 는 경로의 숫자/UUID를 `{id}` 로 템플릿화 → **IDOR 후보** 자동 식별
- 결과는 `reports/web_profile.json` 로 저장 (탐지기 입력으로 재사용)

---

## 7. 진행 상황 요약 (슬라이드 1장 분량)
| 주차 | 항목 | 상태 |
|---|---|---|
| 1 | XSS/SQLi/IDOR 시나리오·판단 기준 정리 | ✅ `docs/vuln-scenarios.md` |
| 1 | 최소 Agent 루프 (LLM→도구→결과) | ✅ Mock + Ollama qwen2.5:7b 실모델 검증 |
| 1 | Selenium 접속/로그인/쿠키 | ✅ |
| 2-3 | 도구 스키마 설계 | ✅ `explore_site` 도구 |
| 2-3 | PageExplorer | ✅ |
| 2-3 | NetworkCollector | ✅ |
| 2-3 | 웹 환경 프로파일 결합 | ✅ InputPoint 도출 |

## 8. 다음 단계 (멘토가 물어볼 것 대비)
- **4주차**: 오케스트레이션 루프 — WebProfile의 InputPoint를 읽어 어떤 탐지기를 돌릴지 판단, 상태 관리, 종료 조건(호출/시간 상한)
- **5-7주차**: XSSDetector / SQLiDetector / IDORDetector
- 실제 LLM: 경량 로컬 모델(Ollama qwen2.5) 세팅 진행 중 → 완료 시 실 모델로 도구 선택 시연

## 9. 알려진 제약 / 정직하게 말할 것
- 아직 **실제 취약점 탐지는 미구현** — 현재는 "공격 표면을 정확히 수집·정규화"하는 단계까지
- 실 LLM(Ollama qwen2.5:7b) 도구 호출은 검증됨. 다만 정찰 파이프라인(데모 C~E)은 아직 규칙 기반 실행이고, LLM이 InputPoint를 읽어 탐지기를 고르는 오케스트레이션은 4주차 예정
- 모든 자동 요청은 **허용된 테스트 사이트에만** 수행 (범용 데모는 공개 연습 사이트 사용)

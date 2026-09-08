"""1주차 예제: LLM이 도구 하나를 호출하고 결과를 받는 최소 Agent 루프.

기본은 MockClient(모델 없이 동작)로 실행되어 루프 구조를 바로 검증할 수 있다.
Ollama 로컬 모델로 실행하려면:

    python examples/minimal_agent_loop.py --backend ollama --model qwen2.5:7b

프로젝트 루트에서 실행:  python examples/minimal_agent_loop.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Windows 콘솔(cp949)에서 한글이 깨지지 않도록 UTF-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

# 프로젝트 루트를 import 경로에 추가 (패키지 설치 없이 실행하기 위함)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.loop import Agent  # noqa: E402
from src.agent.tools import build_example_registry  # noqa: E402
from src.llm.client import ChatResult, MockClient, OllamaClient, ToolCall  # noqa: E402

SYSTEM_PROMPT = (
    "너는 웹 취약점 탐지를 돕는 에이전트다. "
    "사용자의 목표를 달성하기 위해 제공된 도구를 필요할 때 호출하고, "
    "도구 결과를 근거로 간결히 결론을 낸다."
)


def _mock_decide(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> ChatResult:
    """모델 없이도 의미 있는 흐름을 보여주는 규칙 기반 응답.

    1) 아직 도구를 안 썼으면 목표 문장에서 따옴표로 감싼 문자열을 payload로 뽑아
       reflect_probe 를 호출한다.
    2) 도구 결과(role=tool)를 받으면 reflected 여부로 결론을 낸다.
    """
    last = messages[-1] if messages else {}
    if last.get("role") == "tool":
        import json

        data = json.loads(last.get("content", "{}"))
        if data.get("reflected"):
            verdict = "반사 확인됨 → XSS 후보 (컨텍스트: %s)" % data.get("context")
        else:
            verdict = "반사되지 않음 → 이 입력 지점은 후보 아님"
        return ChatResult(content=verdict)

    # 목표 문장에서 "..." 안의 문자열을 payload로 추출
    goal = next((m["content"] for m in messages if m.get("role") == "user"), "")
    payload = "<b>test</b>"
    if '"' in goal:
        payload = goal.split('"')[1]
    return ChatResult(
        tool_calls=[ToolCall(name="reflect_probe", arguments={"payload": payload})]
    )


def make_llm(backend: str, model: str):
    if backend == "ollama":
        client = OllamaClient(model=model)
        if not client.is_available():
            print(
                f"[경고] Ollama 서버 또는 모델({model})을 찾지 못했습니다. "
                "Ollama 설치/실행과 `ollama pull` 을 확인하세요."
            )
        return client
    return MockClient(decide=_mock_decide)


def main() -> None:
    parser = argparse.ArgumentParser(description="최소 Agent 루프 데모")
    parser.add_argument(
        "--backend",
        choices=["mock", "ollama"],
        default="mock",
        help="LLM 백엔드 (기본: mock — 모델 없이 실행)",
    )
    parser.add_argument("--model", default="qwen2.5:7b", help="Ollama 모델 이름")
    parser.add_argument(
        "--goal",
        default="문자열 \"<b>test</b>\" 가 대상에 그대로 반사되는지 확인해줘.",
        help="에이전트에게 줄 목표",
    )
    args = parser.parse_args()

    llm = make_llm(args.backend, args.model)
    registry = build_example_registry()
    agent = Agent(llm, registry, system_prompt=SYSTEM_PROMPT, max_steps=5)

    print(f"=== backend={args.backend} | 등록된 도구 {len(registry)}개 ===")
    print(f"목표: {args.goal}\n")

    result = agent.run(args.goal)

    print("\n=== 최종 결과 ===")
    print(f"단계 수: {result.steps}")
    print(f"응답: {result.final_content}")


if __name__ == "__main__":
    main()

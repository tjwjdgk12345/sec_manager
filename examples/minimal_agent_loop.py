"""1주차 예제: LLM이 도구 하나를 호출하고 결과를 받는 최소 Agent 루프.

로컬 Ollama 모델을 사용한다. 사전에 Ollama 실행 + 모델 pull 이 필요하다:

    ollama pull qwen2.5:7b

실행:
    python examples/minimal_agent_loop.py
    python examples/minimal_agent_loop.py --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 한글이 깨지지 않도록 UTF-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

# 프로젝트 루트를 import 경로에 추가 (패키지 설치 없이 실행하기 위함)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.loop import Agent  # noqa: E402
from src.agent.tools import build_example_registry  # noqa: E402
from src.llm.client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "너는 웹 취약점 탐지를 돕는 에이전트다. "
    "사용자의 목표를 달성하기 위해 제공된 도구를 필요할 때 호출하고, "
    "도구 결과를 근거로 간결히 결론을 낸다."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="최소 Agent 루프 데모")
    parser.add_argument("--model", default="qwen2.5:7b", help="Ollama 모델 이름")
    parser.add_argument(
        "--goal",
        default="문자열 \"<b>test</b>\" 가 대상에 그대로 반사되는지 확인해줘.",
        help="에이전트에게 줄 목표",
    )
    args = parser.parse_args()

    llm = OllamaClient(model=args.model)
    if not llm.is_available():
        print(
            f"[오류] Ollama 서버 또는 모델({args.model})을 찾지 못했습니다.\n"
            "  1) Ollama 실행 확인 (http://localhost:11434)\n"
            f"  2) 모델 준비: ollama pull {args.model}"
        )
        sys.exit(1)

    registry = build_example_registry()
    agent = Agent(llm, registry, system_prompt=SYSTEM_PROMPT, max_steps=5)

    print(f"=== model={args.model} | 등록된 도구 {len(registry)}개 ===")
    print(f"목표: {args.goal}\n")

    result = agent.run(args.goal)

    print("\n=== 최종 결과 ===")
    print(f"단계 수: {result.steps}")
    print(f"응답: {result.final_content}")


if __name__ == "__main__":
    main()

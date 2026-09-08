"""최소 Agent 오케스트레이션 루프.

LLM이 도구를 호출하면 실행하고, 결과를 다시 모델에 돌려주는 것을 반복한다.
무한 루프 방지를 위해 도구 호출 횟수 상한(max_steps)을 둔다.
(4주차에서 상태 관리·종료 조건·시간 상한을 여기서 확장한다.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..llm.client import ChatResult, LLMClient
from .tools import ToolRegistry


@dataclass
class AgentResult:
    final_content: str
    steps: int
    transcript: list[dict[str, Any]] = field(default_factory=list)


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        system_prompt: str | None = None,
        max_steps: int = 5,
        verbose: bool = True,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.verbose = verbose

    def _log(self, *args: Any) -> None:
        if self.verbose:
            print(*args)

    def run(self, user_goal: str) -> AgentResult:
        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_goal})

        tools = self.registry.to_schemas()

        for step in range(1, self.max_steps + 1):
            result: ChatResult = self.llm.chat(messages, tools=tools)

            if not result.wants_tool:
                self._log(f"[step {step}] 모델 최종 응답")
                messages.append({"role": "assistant", "content": result.content})
                return AgentResult(
                    final_content=result.content,
                    steps=step,
                    transcript=messages,
                )

            # 모델이 도구를 호출하기로 함 -> assistant 턴 기록
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in result.tool_calls
                    ],
                }
            )

            for tc in result.tool_calls:
                self._log(f"[step {step}] 도구 호출: {tc.name}({tc.arguments})")
                if tc.name not in self.registry:
                    output: Any = {"error": f"unknown tool: {tc.name}"}
                else:
                    try:
                        output = self.registry.call(tc.name, tc.arguments)
                    except Exception as exc:  # noqa: BLE001 - 도구 오류를 모델에 전달
                        output = {"error": str(exc)}

                self._log(f"          결과: {output}")
                messages.append(
                    {
                        "role": "tool",
                        "name": tc.name,
                        "content": json.dumps(output, ensure_ascii=False),
                    }
                )

        # 상한 도달
        self._log(f"[중단] max_steps({self.max_steps}) 도달")
        return AgentResult(
            final_content="(도구 호출 상한 도달로 종료)",
            steps=self.max_steps,
            transcript=messages,
        )

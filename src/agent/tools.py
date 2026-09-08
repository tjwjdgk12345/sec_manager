"""Agent가 호출할 수 있는 도구(tool) 정의와 레지스트리.

각 도구는:
  - name        : 모델이 부르는 이름
  - description : 언제 쓰는지 (모델이 선택 근거로 사용)
  - parameters  : JSON Schema 형태의 인자 스펙
  - fn          : 실제 실행 함수 (**kwargs 로 인자 전달)

register()로 등록하면 to_ollama_schema()가 Ollama/OpenAI 호환 tools 배열을 만든다.
이 구조는 이후 PageExplorer/NetworkCollector/각 Detector를 도구로 붙일 때 그대로 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    def to_schema(self) -> dict[str, Any]:
        """Ollama/OpenAI 호환 function-tool 스키마."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """데코레이터로 도구 등록."""

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = Tool(name, description, parameters, fn)
            return fn

        return deco

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def to_schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"등록되지 않은 도구: {name!r}")
        return tool.fn(**arguments)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


# --- 1주차 최소 예제 도구 ---------------------------------------------------

def build_example_registry() -> ToolRegistry:
    """LLM이 도구 하나를 호출하고 결과를 받는 최소 루프용 예제 도구 모음."""
    registry = ToolRegistry()

    @registry.register(
        name="reflect_probe",
        description=(
            "주어진 문자열이 그대로 반사되는지 확인하는 모의 프로브. "
            "실제 XSS 반사 탐지의 축소판으로, 입력 마커가 이스케이프 없이 "
            "되돌아오면 reflected=true 를 돌려준다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "string",
                    "description": "반사 여부를 확인할 마커 문자열",
                }
            },
            "required": ["payload"],
        },
    )
    def reflect_probe(payload: str) -> dict[str, Any]:
        # 모의 대상: '<' 를 이스케이프하지 않고 그대로 되돌려주는 취약한 서버라고 가정
        reflected = "<" in payload  # 데모용 규칙
        return {
            "payload": payload,
            "reflected": reflected,
            "context": "html_body",
            "note": "데모용 모의 응답 (실제 HTTP 요청 아님)",
        }

    return registry

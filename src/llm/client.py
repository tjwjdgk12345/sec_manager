"""LLM 클라이언트 추상화.

계획서 제약(경량 로컬 모델)에 맞춰 기본 백엔드는 Ollama이지만,
Agent 코드가 특정 제공자에 묶이지 않도록 공통 인터페이스(LLMClient)로 감싼다.
나중에 다른 제공자를 붙이려면 chat()만 같은 형태로 구현하면 된다.

- OllamaClient : 로컬 Ollama 서버(http://localhost:11434) 호출

tool calling(도구 호출)을 지원하는 chat() 하나로 통일한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests


@dataclass
class ToolCall:
    """모델이 호출하기로 결정한 도구 하나."""

    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    """chat() 한 번의 결과. 도구 호출이 있으면 tool_calls가 채워진다."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    """Agent 루프가 의존하는 최소 인터페이스."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        ...


class OllamaClient:
    """로컬 Ollama 서버를 호출하는 클라이언트.

    사전 준비:
      1) https://ollama.com 에서 Ollama 설치
      2) 도구 호출 지원 모델 pull (예: `ollama pull qwen2.5:7b`)
      3) 서버 실행(설치 시 자동) — 기본 포트 11434
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        host: str = "http://localhost:11434",
        timeout: int = 300,  # 콜드 스타트(모델을 메모리에 처음 로드) 대비 넉넉히
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        resp = requests.post(
            f"{self.host}/api/chat", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {}) or {}

        tool_calls: list[ToolCall] = []
        for call in message.get("tool_calls", []) or []:
            fn = call.get("function", {}) or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args or {}))

        return ChatResult(
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            raw=data,
        )

    def is_available(self) -> bool:
        """서버가 떠 있고 지정 모델이 있는지 가볍게 확인."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
            # 태그 없이 지정한 경우도 느슨하게 매칭
            return any(n == self.model or n.startswith(self.model) for n in names)
        except requests.RequestException:
            return False

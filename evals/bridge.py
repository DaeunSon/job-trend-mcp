"""
MCP 서버를 in-memory 로 띄워, 도구 정의를 Claude API tools 형식으로 바꾸고 호출을 대신 실행한다.

Claude Desktop 이 보는 것과 같은 도구 이름 · 설명 · 입력 스키마를 그대로 쓰기 위해
도구 정의를 코드에 다시 적지 않고 MCP list_tools 결과에서 만든다.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import AsyncExitStack
from typing import Any

from mcp import Client


class McpBridge:
    def __init__(self) -> None:
        # server import 시점에 job_postings 를 로드하므로, 로그 경로 설정 뒤에 import 한다.
        from src.mcp_server.server import mcp

        self._server = mcp
        self._stack = AsyncExitStack()
        self._client: Client | None = None
        self.tool_defs: list[dict[str, Any]] = []

    async def __aenter__(self) -> "McpBridge":
        self._client = await self._stack.enter_async_context(
            Client(self._server, raise_exceptions=True)
        )
        listed = await self._client.list_tools()
        self.tool_defs = [
            {
                "name": t.name,
                "description": (t.description or t.title or t.name).strip(),
                "input_schema": t.input_schema,
            }
            for t in listed.tools
        ]
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    @property
    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.tool_defs]

    def tools_hash(self) -> str:
        """도구 설명 · 스키마 버전. 설명을 고치면 값이 바뀐다."""
        blob = json.dumps(self.tool_defs, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:8]

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """도구를 실행해 structured content 를 돌려준다. 실패는 예외 대신 status=error 로 돌려준다."""
        assert self._client is not None
        if name not in self.tool_names:
            return {"status": "error", "message": f"unknown tool {name!r}"}
        try:
            result = await self._client.call_tool(name, args)
        except Exception as exc:  # 잘못된 인자 타입 등 — 모델에게 그대로 알려 준다
            return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
        if result.structured_content is not None:
            return dict(result.structured_content)
        text = "".join(getattr(c, "text", "") for c in result.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"status": "error" if result.is_error else "ok", "message": text}

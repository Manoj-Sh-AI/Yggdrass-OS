"""Talking to a connected app's MCP server over Streamable HTTP (the official `mcp` SDK).

Each call opens a short session with the current access token, does one thing and closes.
Results go back to the task that asked and are never stored (Manoj's privacy choice).
"""

from __future__ import annotations

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MAX_RESULT = 20000


class MCPError(RuntimeError):
    pass


async def _session(url: str, token: str, work):
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(30, read=120)
    async with (
        httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await work(session)


def list_tools(url: str, token: str) -> list[dict]:
    async def work(session):
        tools, cursor = [], None
        while True:
            page = await session.list_tools(cursor) if cursor else await session.list_tools()
            for t in page.tools:
                annotations = t.annotations.model_dump(exclude_none=True) if t.annotations else {}
                tools.append({"name": t.name, "description": t.description or "",
                              "inputSchema": t.inputSchema or {"type": "object"},
                              "annotations": annotations})  # fmt: skip
            cursor = page.nextCursor
            if not cursor or len(tools) > 500:
                return tools

    try:
        return anyio.run(_session, url, token, work)
    except Exception as exc:  # noqa: BLE001 - the message never carries the token
        raise MCPError(f"The app's tools could not be listed ({type(exc).__name__}).") from None


def call_tool(url: str, token: str, name: str, arguments: dict) -> dict:
    async def work(session):
        result = await session.call_tool(name, arguments or {})
        text = "\n".join(
            getattr(block, "text", "") for block in result.content if getattr(block, "text", "")
        )
        return {"error": bool(result.isError), "text": text[:MAX_RESULT],
                "truncated": len(text) > MAX_RESULT}  # fmt: skip

    try:
        return anyio.run(_session, url, token, work)
    except Exception as exc:  # noqa: BLE001
        raise MCPError(f"The app did not answer ({type(exc).__name__}).") from None

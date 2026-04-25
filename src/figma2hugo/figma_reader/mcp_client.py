from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx


class FigmaMcpError(RuntimeError):
    """Raised when the optional MCP bridge cannot be used."""


@dataclass(slots=True)
class McpServerConfig:
    transport: str
    url: str | None
    command: str | None
    args: list[str]
    bearer_token: str | None

    @classmethod
    def from_env(cls) -> "McpServerConfig":
        return cls(
            transport=os.getenv("FIGMA_MCP_TRANSPORT", "streamable-http"),
            url=os.getenv("FIGMA_MCP_URL", "https://mcp.figma.com/mcp"),
            command=os.getenv("FIGMA_MCP_COMMAND"),
            args=json.loads(os.getenv("FIGMA_MCP_ARGS", "[]")),
            bearer_token=os.getenv("FIGMA_MCP_BEARER_TOKEN"),
        )


class FigmaMcpClient:
    """Best-effort MCP client for Figma-compatible tool bridges.

    The official remote server requires OAuth and some clients wrap that flow for you.
    This adapter assumes either:
    - a compatible Streamable HTTP bridge already exposing the Figma tools, or
    - a local stdio MCP server command.

    Tool arguments use the common `{"url": <figma-url>}` shape used by several
    compatible bridges. When a bridge expects different arguments, callers should
    set up a thin proxy instead of editing the pipeline.
    """

    def __init__(self, config: McpServerConfig | None = None) -> None:
        self.config = config or McpServerConfig.from_env()

    @property
    def available(self) -> bool:
        if self.config.transport == "stdio":
            return bool(self.config.command)
        return bool(self.config.url)

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise FigmaMcpError(
                "The optional `mcp` package is required for FIGMA_MCP_* integration."
            ) from exc

        @asynccontextmanager
        async def session_context():
            if self.config.transport == "stdio":
                if not self.config.command:
                    raise FigmaMcpError("FIGMA_MCP_COMMAND is required when FIGMA_MCP_TRANSPORT=stdio.")
                async with stdio_client(command=self.config.command, args=self.config.args) as streams:
                    read, write = streams
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
                return

            if not self.config.url:
                raise FigmaMcpError("FIGMA_MCP_URL is required when FIGMA_MCP_TRANSPORT=streamable-http.")
            headers: dict[str, str] = {}
            if self.config.bearer_token:
                headers["Authorization"] = f"Bearer {self.config.bearer_token}"
            async with httpx.AsyncClient(headers=headers, timeout=90.0, follow_redirects=True) as client:
                async with streamable_http_client(self.config.url, http_client=client) as streams:
                    read, write, _ = streams
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session

        async with session_context() as session:
            result = await session.call_tool(tool_name, arguments)
            payload: dict[str, Any] = {"content": []}
            for item in getattr(result, "content", []):
                item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                payload["content"].append(item_dict)
            payload["is_error"] = getattr(result, "isError", False)
            return payload

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call_tool_async(tool_name, arguments))

    def get_metadata(self, figma_url: str) -> dict[str, Any]:
        return self.call_tool("get_metadata", {"url": figma_url})

    def get_design_context(self, figma_url: str) -> dict[str, Any]:
        return self.call_tool("get_design_context", {"url": figma_url, "framework": "html-css"})

    def get_variable_defs(self, figma_url: str) -> dict[str, Any]:
        return self.call_tool("get_variable_defs", {"url": figma_url})

    def get_screenshot(self, figma_url: str) -> dict[str, Any]:
        return self.call_tool("get_screenshot", {"url": figma_url})

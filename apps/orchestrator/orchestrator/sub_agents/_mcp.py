"""Helpers for wiring MCP tool servers into ADK sub-agents.

Three transports are supported, picked via `MCP_TRANSPORT`:
  - "stdio" (default, local dev): each MCP server runs as a node subprocess.
  - "http"  (production, Cloud Run): Streamable HTTP at MCP_<SVC>_URL.
  - "sse"   (legacy fallback): Server-Sent Events at MCP_<SVC>_URL.
"""

from __future__ import annotations

import os

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters


def _stdio_toolset(mcp_app_dir: str, tool_filter: list[str] | None = None) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="node",
                args=[os.path.join(mcp_app_dir, "dist", "index.js")],
                env={**os.environ},
            ),
            timeout=10,
        ),
        tool_filter=tool_filter,
    )


def _remote_toolset(
    service: str,
    transport: str,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    url = os.environ[f"MCP_{service.upper()}_URL"]
    headers: dict[str, str] = {}
    auth_token = os.environ.get("MCP_BEARER_TOKEN", "")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if transport == "sse":
        params = SseConnectionParams(url=url, headers=headers)
    else:
        params = StreamableHTTPConnectionParams(url=url, headers=headers)
    return McpToolset(connection_params=params, tool_filter=tool_filter)


def build_mcp_toolset(
    service: str,
    *,
    tool_filter: list[str] | None = None,
) -> McpToolset:
    """Pick the right transport per the MCP_TRANSPORT env var."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport in {"http", "sse"}:
        return _remote_toolset(service, transport, tool_filter=tool_filter)
    repo_root = os.environ.get(
        "COPILOT_REPO_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")),
    )
    return _stdio_toolset(
        os.path.join(repo_root, "apps", f"mcp-{service}"),
        tool_filter=tool_filter,
    )

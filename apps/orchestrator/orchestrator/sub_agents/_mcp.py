"""Helpers for wiring MCP tool servers into ADK sub-agents.

Three transports, picked via `MCP_TRANSPORT`:
  - "stdio" (default, local dev): each MCP server runs as a node subprocess.
  - "http"  (production, Cloud Run): Streamable HTTP at MCP_<SVC>_URL.
  - "sse"   (legacy fallback): Server-Sent Events at MCP_<SVC>_URL.

Auth for the http/sse path:
  - On Cloud Run we fetch a Google-signed OIDC ID token from the metadata
    server for the target MCP service's audience and inject it as
    `Authorization: Bearer <id_token>`. Cloud Run validates the signature
    upstream and only routes the request to the container if the runtime
    service account (`copilot-runtime@…`) is bound as `roles/run.invoker`
    on that MCP service.
  - The token's audience is the bare service URL (without the `/mcp` path);
    we strip the path before requesting it.
  - On environments where the metadata server is not reachable (local
    `MCP_TRANSPORT=http` testing), we fall back to a static
    `MCP_BEARER_TOKEN` header, which the MCP server validates with
    `crypto.timingSafeEqual` (see docs/SECURITY.md).
  - Limitation we accept for Day 3: the ID token is fetched once at agent
    build time and lives for ~1h. Cloud Run instances idle out long before
    that. Day 4-5 punch list adds a `httpx`-level auth hook that refreshes
    on 401. Documented as Gap 5 in SECURITY.md.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse, urlunparse

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

logger = logging.getLogger("orchestrator.mcp")


def _audience_from_url(url: str) -> str:
    """Strip path/query so the audience matches the Cloud Run service URL."""
    parts = urlparse(url)
    return urlunparse((parts.scheme, parts.netloc, "", "", "", ""))


def _fetch_id_token(audience: str) -> str | None:
    """Get a Google-signed OIDC ID token for the audience (Cloud Run path)."""
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        request = google.auth.transport.requests.Request()
        return google.oauth2.id_token.fetch_id_token(request, audience)
    except Exception as exc:
        logger.warning("ID token fetch for %s failed: %s", audience, exc)
        return None


def _remote_auth_headers(url: str) -> dict[str, str]:
    """Build the Authorization header for the http/sse transport."""
    audience = _audience_from_url(url)
    id_token = _fetch_id_token(audience)
    if id_token:
        logger.info("mcp[%s] using OIDC id_token", audience)
        return {"Authorization": f"Bearer {id_token}"}
    static_bearer = os.environ.get("MCP_BEARER_TOKEN", "")
    if static_bearer:
        logger.info("mcp[%s] using static MCP_BEARER_TOKEN fallback", audience)
        return {"Authorization": f"Bearer {static_bearer}"}
    logger.warning("mcp[%s] no auth header available", audience)
    return {}


def _stdio_toolset(
    mcp_app_dir: str,
    tool_filter: list[str] | None = None,
) -> McpToolset:
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
    headers = _remote_auth_headers(url)
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

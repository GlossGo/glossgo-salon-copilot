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
        # NEVER log the token; only the exception type/message.
        print(f"[mcp] id_token fetch for {audience} FAILED: {type(exc).__name__}: {exc}", flush=True)
        return None


def _remote_auth_headers(url: str) -> dict[str, str]:
    """Build headers for the http/sse transport.

    The MCP Streamable HTTP spec requires `Accept: application/json,
    text/event-stream`. Some httpx defaults strip the second media type;
    set it explicitly here.

    Auth selection (NEVER log token contents — even partial JWTs leak
    headers/audience/exp claims):
      1. Static `MCP_BEARER_TOKEN` (matches what the MCP container's
         Express middleware verifies with `crypto.timingSafeEqual`).
         This is the primary auth layer today.
      2. If `MCP_USE_OIDC=1` AND no static bearer is set, fetch an OIDC
         ID token from the Cloud Run metadata server. We keep this code
         path for when Day 6 lands the matching server-side validator
         that accepts Google-signed tokens with `audience == service_url`.
         Until then, Cloud Run rejected our OIDC tokens with
         "access token could not be verified" — see SECURITY.md Gap 1.
    """
    audience = _audience_from_url(url)
    headers: dict[str, str] = {
        "Accept": "application/json, text/event-stream",
    }
    static_bearer = os.environ.get("MCP_BEARER_TOKEN", "")
    if static_bearer:
        print(f"[mcp] {audience} auth=static-bearer", flush=True)
        headers["Authorization"] = f"Bearer {static_bearer}"
        return headers
    if os.environ.get("MCP_USE_OIDC", "0") == "1":
        id_token = _fetch_id_token(audience)
        if id_token:
            print(f"[mcp] {audience} auth=oidc", flush=True)
            headers["Authorization"] = f"Bearer {id_token}"
            return headers
    print(f"[mcp] {audience} auth=NONE", flush=True)
    return headers


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

"""HTTP entry point for the orchestrator (runs on Cloud Run).

Exposes two routes:
  POST /event    Body: {"type": "booking.cancelled", "business_id": "...", "booking_id": "..."}
                 -> runs the root agent on the event payload, returns the action log.
                 Requires `Authorization: Bearer <COPILOT_WEBHOOK_BEARER>` header.
  GET  /ready    Liveness probe (unauthenticated). Renamed from /healthz because
                 Cloud Run's Google Frontend reserves /healthz and returns 404
                 for external requests even when the container registers it.

In production this endpoint is fronted by a Pub/Sub push subscription that
forwards a Google-signed OIDC token; the bearer secret is a stopgap that
also covers manual curl runs from the demo + the Cloudflare Worker forwarder.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import secrets
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from orchestrator.agent import root_agent

load_dotenv()

WEBHOOK_BEARER = os.environ.get("COPILOT_WEBHOOK_BEARER", "")
if not WEBHOOK_BEARER or len(WEBHOOK_BEARER) < 16:
    # Fail-closed: refuse to boot a public endpoint without a real secret.
    # For local dev, set COPILOT_WEBHOOK_BEARER=$(openssl rand -hex 32).
    raise RuntimeError(
        "orchestrator: COPILOT_WEBHOOK_BEARER must be set (>=16 chars). "
        "Generate one with `openssl rand -hex 32`."
    )

_EXPECTED_AUTH = f"Bearer {WEBHOOK_BEARER}".encode()
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

app = FastAPI(title="glossgo Salon Co-Pilot Orchestrator", version="0.1.0")
_runner = InMemoryRunner(agent=root_agent, app_name="glossgo-copilot")


def _require_bearer(authorization: str | None) -> None:
    if not authorization or not hmac.compare_digest(
        authorization.encode(), _EXPECTED_AUTH
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ok", "agent": root_agent.name}


# ---------------------------------------------------------------------------
# /dashboard — minimal owner-facing view of agent activity.
# Reads from the same `copilot.*` Supabase schema the MCP servers write to.
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


async def _supabase_get(path: str, params: dict[str, str]) -> list[dict[str, object]]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{path}",
            params=params,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Accept-Profile": "copilot",
            },
        )
        if resp.status_code >= 300:
            return []
        return resp.json()


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _ts(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


def _row_html(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


DASHBOARD_TOKEN = os.environ.get("COPILOT_DASHBOARD_TOKEN", "") or WEBHOOK_BEARER
_DASHBOARD_AUTH = f"Bearer {DASHBOARD_TOKEN}".encode()


def _require_dashboard_token(authorization: str | None, query_token: str | None) -> None:
    """Accept either Authorization: Bearer <tok> OR ?token=<tok> on dashboard routes.

    Both endpoints — read AND state-changing — go through this. Single token
    today is the same as COPILOT_WEBHOOK_BEARER; production swaps for a
    per-owner signed session (see SECURITY.md Gap 6, Day 6 plan).
    """
    if not DASHBOARD_TOKEN or len(DASHBOARD_TOKEN) < 16:
        raise HTTPException(
            status_code=503,
            detail="dashboard disabled: COPILOT_DASHBOARD_TOKEN not configured",
        )
    if authorization and hmac.compare_digest(authorization.encode(), _DASHBOARD_AUTH):
        return
    if query_token and hmac.compare_digest(
        f"Bearer {query_token}".encode(), _DASHBOARD_AUTH
    ):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    token: str | None = None,
    authorization: str | None = Header(default=None),
) -> str:
    _require_dashboard_token(authorization, token)
    actions = await _supabase_get(
        "agent_actions",
        {"select": "id,business_id,kind,payload,shadow,created_at",
         "order": "created_at.desc", "limit": "25"},
    )
    queue = await _supabase_get(
        "owner_approval_queue",
        {"select": "id,business_id,channel,payload,status,created_at",
         "status": "eq.pending",
         "order": "created_at.desc", "limit": "25"},
    )

    actions_rows = "\n".join(
        _row_html([
            _ts(a.get("created_at")),
            _esc(a.get("kind")),
            "✓ shadow" if a.get("shadow") else "<b>LIVE</b>",
            _esc(str(a.get("payload", ""))[:140]),
        ])
        for a in actions
    ) or _row_html(["—", "<i>no agent actions yet</i>", "", ""])

    tok_q = f"?token={_esc(token)}" if token else ""
    queue_rows = "\n".join(
        _row_html([
            _ts(q.get("created_at")),
            _esc(q.get("channel")),
            _esc(str(q.get("payload", ""))[:200]),
            f'<form method="post" action="/dashboard/{q.get("id")}/approve{tok_q}">'
            '<button>approve</button></form>',
        ])
        for q in queue
    ) or _row_html(["—", "<i>queue empty</i>", "", ""])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>glossgo Salon Co-Pilot — agent dashboard</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; max-width: 980px; margin: 32px auto;
          padding: 0 24px; color: #1c1924; background: #faf8fb; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .meta {{ color: #64596f; margin-bottom: 32px; }}
  h2 {{ font-size: 16px; margin: 28px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 3px rgba(20,5,40,.06); }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ece4f1;
            vertical-align: top; }}
  th {{ background: #f4eef7; font-weight: 600; color: #3c2b50; }}
  tr:last-child td {{ border-bottom: none; }}
  td:nth-child(4) {{ font-family: ui-monospace, Menlo, monospace; font-size: 12px;
                      color: #4a3e5a; }}
  form {{ margin: 0; }}
  button {{ background: #6f3aac; color: #fff; border: none; padding: 4px 10px;
            border-radius: 4px; font: inherit; cursor: pointer; }}
</style></head>
<body>
<h1>glossgo Salon Co-Pilot</h1>
<p class="meta">Agent activity, read-only.
Source: <code>copilot.agent_actions</code> + <code>copilot.owner_approval_queue</code>.
Refresh to see the latest events.</p>

<h2>Pending owner approvals</h2>
<table><thead><tr><th>when</th><th>channel</th><th>payload</th><th></th></tr></thead>
<tbody>{queue_rows}</tbody></table>

<h2>Recent agent actions</h2>
<table><thead><tr><th>when</th><th>kind</th><th>mode</th><th>payload</th></tr></thead>
<tbody>{actions_rows}</tbody></table>
</body></html>"""


@app.post("/dashboard/{approval_id}/approve")
async def approve(
    approval_id: str,
    token: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _require_dashboard_token(authorization, token)
    if not _UUID_RE.match(approval_id):
        raise HTTPException(status_code=400, detail="invalid id")
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="supabase not configured")

    # Confirm the row exists, is still pending, and load its business_id. Any
    # production multi-tenant version of this endpoint would also verify the
    # caller's business_id claim matches row.business_id here (SECURITY.md
    # Gap 6 — owner identity replaces single shared token).
    existing = await _supabase_get(
        "owner_approval_queue",
        {"id": f"eq.{approval_id}", "status": "eq.pending",
         "select": "id,business_id,status"},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="not found or already acted")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/owner_approval_queue",
            params={"id": f"eq.{approval_id}", "status": "eq.pending"},
            json={"status": "approved", "acted_at": dt.datetime.now(dt.UTC).isoformat()},
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Accept-Profile": "copilot",
                "Content-Profile": "copilot",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        if resp.status_code >= 300:
            raise HTTPException(status_code=502, detail=f"supabase: {resp.status_code}")
    return {"id": approval_id, "status": "approved"}


@app.post("/event")
async def handle_event(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    _require_bearer(authorization)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc

    event_type = payload.get("type")
    if not event_type:
        raise HTTPException(status_code=400, detail="missing 'type'")
    business_id = payload.get("business_id")
    if not business_id or not _UUID_RE.match(str(business_id)):
        raise HTTPException(status_code=400, detail="missing/invalid 'business_id'")

    user_message = (
        f"A new salon event has arrived. Route it appropriately.\n\n"
        f"Event payload (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    session_id = payload.get("session_id") or f"evt-{uuid.uuid4().hex[:12]}"
    # Tenant scope is the verified business_id from the (Bearer-)authenticated
    # caller. We trust the bearer to be glossgo-be (which proves the tenant at
    # event-emit time); Cloud Run service identity will replace this Day 2.
    user_id = str(business_id)

    session = await _runner.session_service.create_session(
        app_name=_runner.app_name,
        user_id=user_id,
        session_id=session_id,
    )

    final_text: list[str] = []
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=user_message)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text.append(part.text)

    return {
        "session_id": session.id,
        "event_type": event_type,
        "agent_response": "\n".join(final_text).strip(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=False,
    )

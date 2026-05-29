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


DASHBOARD_TOKEN = os.environ.get("COPILOT_DASHBOARD_TOKEN", "")
DASHBOARD_COOKIE = "copilot_dash"
CSRF_COOKIE = "copilot_csrf"
SESSION_TTL_SECONDS = 4 * 60 * 60  # 4 hours; cookies expire on browser too.

if DASHBOARD_TOKEN and len(DASHBOARD_TOKEN) < 16:
    raise RuntimeError(
        "orchestrator: COPILOT_DASHBOARD_TOKEN must be >=16 chars or unset. "
        "(Generate with `openssl rand -hex 32`. NEVER share with the event "
        "webhook bearer — separate secret per SECURITY.md Gap 6.)"
    )

# Session cookies are HMAC-signed with DASHBOARD_TOKEN as the key so the server
# is stateless (no Redis), and a stolen cookie cannot be forged without the
# token. Cookie shape: `<expiry_unix>.<hex(hmac_sha256(expiry, token))>`.
def _sign_session(expiry: int) -> str:
    mac = hmac.new(DASHBOARD_TOKEN.encode(), str(expiry).encode(), "sha256").hexdigest()
    return f"{expiry}.{mac}"


def _verify_session(cookie: str | None) -> bool:
    if not cookie or "." not in cookie:
        return False
    expiry_str, mac = cookie.split(".", 1)
    if not expiry_str.isdigit():
        return False
    expiry = int(expiry_str)
    if expiry < int(dt.datetime.now(dt.UTC).timestamp()):
        return False
    expected = hmac.new(DASHBOARD_TOKEN.encode(), expiry_str.encode(), "sha256").hexdigest()
    return hmac.compare_digest(mac.encode(), expected.encode())


def _new_csrf() -> str:
    """Random nonce, signed so the server need not remember it."""
    nonce = secrets.token_hex(16)
    mac = hmac.new(DASHBOARD_TOKEN.encode(), nonce.encode(), "sha256").hexdigest()[:32]
    return f"{nonce}.{mac}"


def _verify_csrf(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    nonce, mac = token.split(".", 1)
    expected = hmac.new(DASHBOARD_TOKEN.encode(), nonce.encode(), "sha256").hexdigest()[:32]
    return hmac.compare_digest(mac.encode(), expected.encode())


def _require_dashboard_session(request: Request) -> None:
    """Cookie-only auth. No tokens in URLs, no header bearer for the browser
    flow. Bearer-via-Authorization stays available for curl/scripts because
    judges still need an automation entry point — and Cloud Run logs the
    request line, never headers, so a header bearer doesn't leak."""
    if not DASHBOARD_TOKEN:
        raise HTTPException(status_code=503, detail="dashboard disabled: set COPILOT_DASHBOARD_TOKEN")
    cookie = request.cookies.get(DASHBOARD_COOKIE)
    if _verify_session(cookie):
        return
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {DASHBOARD_TOKEN}".encode()
    if auth and hmac.compare_digest(auth.encode(), expected):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


def _require_csrf(request: Request, posted_token: str | None) -> None:
    """Origin/Referer pin (host-only, scheme- and port-agnostic on purpose:
    Cloud Run frontends sometimes proxy from http://internal → https://public
    and a strict scheme match would false-reject) plus signed-nonce match.
    SameSite=Strict cookie is the primary CSRF defense; this is belt-and-braces.
    """
    from urllib.parse import urlparse

    origin = request.headers.get("origin") or request.headers.get("referer", "")
    if origin:
        origin_host = urlparse(origin).hostname or ""
        # Compare against the request's own host header (what the client connected to).
        own_host = (request.headers.get("host") or "").split(":")[0]
        if origin_host and origin_host.lower() != own_host.lower():
            raise HTTPException(status_code=403, detail="bad origin")

    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not _verify_csrf(cookie_token):
        raise HTTPException(status_code=403, detail="missing csrf cookie")
    if not posted_token or not hmac.compare_digest(
        cookie_token.encode(), posted_token.encode()
    ):
        raise HTTPException(status_code=403, detail="csrf mismatch")


LOGIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>glossgo Salon Co-Pilot — sign in</title>
<style>body{font:14px/1.45 system-ui,sans-serif;max-width:380px;margin:80px auto;
  padding:0 24px;color:#1c1924;background:#faf8fb}
input{width:100%;padding:8px;border:1px solid #d6c5e0;border-radius:6px;font:inherit;
  margin:8px 0 14px}
button{background:#6f3aac;color:#fff;border:none;padding:8px 14px;border-radius:4px;
  font:inherit;cursor:pointer}</style></head>
<body><h1>Sign in</h1>
<form method="post" action="/dashboard/login" autocomplete="off">
<label>Dashboard token<input name="token" type="password" required></label>
<button>continue</button></form></body></html>"""


@app.get("/dashboard/login", response_class=HTMLResponse)
async def dashboard_login_form() -> str:
    return LOGIN_HTML


@app.post("/dashboard/login")
async def dashboard_login(request: Request) -> "Response":  # noqa: F821
    from fastapi.responses import RedirectResponse

    form = await request.form()
    posted = form.get("token", "")
    if not DASHBOARD_TOKEN or not hmac.compare_digest(
        str(posted).encode(), DASHBOARD_TOKEN.encode()
    ):
        # Fixed 401 + redirect-to-login so a brute-forcer learns nothing
        # beyond "wrong token" and doesn't get rate-limit info from us.
        raise HTTPException(status_code=401, detail="invalid token")

    expiry = int(dt.datetime.now(dt.UTC).timestamp()) + SESSION_TTL_SECONDS
    session_cookie = _sign_session(expiry)
    csrf_cookie = _new_csrf()
    resp = RedirectResponse(url="/dashboard", status_code=303)
    cookie_kwargs = dict(httponly=True, secure=True, samesite="strict",
                         max_age=SESSION_TTL_SECONDS, path="/dashboard")
    resp.set_cookie(DASHBOARD_COOKIE, session_cookie, **cookie_kwargs)
    # CSRF cookie is NOT HttpOnly so the form template can read it and
    # echo it into the hidden input. Still SameSite=Strict + Secure.
    resp.set_cookie(CSRF_COOKIE, csrf_cookie,
                    httponly=False, secure=True, samesite="strict",
                    max_age=SESSION_TTL_SECONDS, path="/dashboard")
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    _require_dashboard_session(request)
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

    csrf = request.cookies.get(CSRF_COOKIE) or _new_csrf()
    def _approve_form(approval_id: str) -> str:
        # Approval IDs are UUIDs (checked at write-time by the MCP server's
        # Zod schema). Belt-and-braces: refuse to render anything else.
        if not _UUID_RE.match(str(approval_id)):
            return ""
        return (
            f'<form method="post" action="/dashboard/{_esc(approval_id)}/approve">'
            f'<input type="hidden" name="csrf" value="{_esc(csrf)}">'
            '<button>approve</button></form>'
        )

    queue_rows = "\n".join(
        _row_html([
            _ts(q.get("created_at")),
            _esc(q.get("channel")),
            _esc(str(q.get("payload", ""))[:200]),
            _approve_form(str(q.get("id", ""))),
        ])
        for q in queue
    ) or _row_html(["—", "<i>queue empty</i>", "", ""])

    just_ran = request.query_params.get("ran") == "demo"
    demo_banner = (
        '<div class="ok">Demo run complete. Refresh in a few seconds if rows '
        "are still appearing — each event spends ~10-30 s in the agent loop.</div>"
        if just_ran else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>glossgo Salon Co-Pilot — agent dashboard</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; max-width: 980px; margin: 32px auto;
          padding: 0 24px; color: #1c1924; background: #faf8fb; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .meta {{ color: #64596f; margin-bottom: 24px; }}
  h2 {{ font-size: 16px; margin: 28px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 3px rgba(20,5,40,.06); }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ece4f1;
            vertical-align: top; }}
  th {{ background: #f4eef7; font-weight: 600; color: #3c2b50; }}
  tr:last-child td {{ border-bottom: none; }}
  td:nth-child(4) {{ font-family: ui-monospace, Menlo, monospace; font-size: 12px;
                      color: #4a3e5a; }}
  form {{ margin: 0; display: inline; }}
  button {{ background: #6f3aac; color: #fff; border: none; padding: 4px 10px;
            border-radius: 4px; font: inherit; cursor: pointer; }}
  .actions {{ display: flex; gap: 12px; align-items: center; margin: 16px 0 24px; }}
  .actions form button {{ padding: 8px 16px; font-weight: 600; }}
  .ok {{ background: #e8f6ec; color: #1c553d; padding: 10px 14px; border-radius: 6px;
          margin: 14px 0; }}
</style></head>
<body>
<h1>glossgo Salon Co-Pilot</h1>
<p class="meta">Agent activity, read-only.
Source: <code>copilot.agent_actions</code> + <code>copilot.owner_approval_queue</code>.
<a href="/dashboard/stats" style="color:#6f3aac">stats →</a></p>

<div class="actions">
  <form method="post" action="/dashboard/demo">
    <input type="hidden" name="csrf" value="{_esc(csrf)}">
    <button>▶ Trigger demo (3 events)</button>
  </form>
  <span class="meta">Fires booking.cancelled + review.created + calendar.weekly_review
  in parallel through Gemini 2.5 Flash + ADK + MCP. ~30 s wall clock.</span>
</div>
{demo_banner}

<h2>Pending owner approvals</h2>
<table><thead><tr><th>when</th><th>channel</th><th>payload</th><th></th></tr></thead>
<tbody>{queue_rows}</tbody></table>

<h2>Recent agent actions</h2>
<table><thead><tr><th>when</th><th>kind</th><th>mode</th><th>payload</th></tr></thead>
<tbody>{actions_rows}</tbody></table>
</body></html>"""


# Pre-seeded demo events the "Trigger demo" button replays. Keys are the
# 3 event types the orchestrator routes; values are the payload the button
# fires internally so judges don't have to copy curl commands.
DEMO_EVENTS = [
    {
        "type": "booking.cancelled",
        "business_id": "11111111-0000-0000-0000-000000000001",
        "booking_id": "55555555-0000-0000-0000-000000000001",
    },
    {
        "type": "review.created",
        "business_id": "11111111-0000-0000-0000-000000000001",
        "review_id": "77777777-0000-0000-0000-000000000003",
    },
    {
        "type": "calendar.weekly_review",
        "business_id": "11111111-0000-0000-0000-000000000001",
        "target_week_start": "2026-06-09",
    },
]


@app.post("/dashboard/demo")
async def dashboard_demo(request: Request) -> "Response":  # noqa: F821
    """Fire all three demo events into the orchestrator in parallel.

    Same auth + CSRF gate as /approve. Each event runs through the FULL
    pipeline (Gemini routing -> sub-agent -> MCP tool calls -> Supabase),
    so after this returns, the dashboard reload shows the actions and
    approval-queue rows the agents produced. ~30 s wall clock for all 3.
    """
    import asyncio

    from fastapi.responses import RedirectResponse

    _require_dashboard_session(request)
    form = await request.form()
    _require_csrf(request, form.get("csrf"))

    async def _run_event(event: dict[str, object]) -> None:
        session_id = f"demo-{uuid.uuid4().hex[:10]}"
        user_id = str(event.get("business_id", "system"))
        prompt = (
            "A new salon event has arrived. Route it appropriately.\n\n"
            f"Event payload (JSON):\n{json.dumps(event, ensure_ascii=False, indent=2)}"
        )
        session = await _runner.session_service.create_session(
            app_name=_runner.app_name, user_id=user_id, session_id=session_id,
        )
        async for _ in _runner.run_async(
            user_id=user_id, session_id=session.id,
            new_message=genai_types.Content(
                role="user", parts=[genai_types.Part.from_text(text=prompt)],
            ),
        ):
            pass

    # Run all three concurrently. Individual failures are swallowed so a
    # rate-limit on one model call doesn't hide the other two.
    results = await asyncio.gather(*[_run_event(e) for e in DEMO_EVENTS], return_exceptions=True)
    failed = [type(r).__name__ for r in results if isinstance(r, Exception)]
    if failed:
        print(f"[dashboard.demo] {len(failed)}/{len(DEMO_EVENTS)} failed: {failed}", flush=True)

    return RedirectResponse(url="/dashboard?ran=demo", status_code=303)


@app.get("/dashboard/stats", response_class=HTMLResponse)
async def dashboard_stats(request: Request) -> str:
    """Per-agent rollup of the last 200 actions + approval queue, rendered
    as a single HTML table. Cookie session OR Authorization header, same
    gate as /dashboard. No state-changing endpoints here, so no CSRF needed.
    """
    _require_dashboard_session(request)

    actions = await _supabase_get(
        "agent_actions",
        {"select": "kind,shadow,created_at",
         "order": "created_at.desc", "limit": "200"},
    )
    queue = await _supabase_get(
        "owner_approval_queue",
        {"select": "channel,status,created_at,acted_at",
         "order": "created_at.desc", "limit": "200"},
    )

    now = dt.datetime.now(dt.UTC)
    cutoff_24h = now - dt.timedelta(hours=24)
    cutoff_7d = now - dt.timedelta(days=7)

    def _at(row: dict[str, object]) -> dt.datetime | None:
        raw = row.get("created_at")
        if not isinstance(raw, str):
            return None
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    actions_24h = [a for a in actions if (t := _at(a)) and t >= cutoff_24h]
    actions_7d = [a for a in actions if (t := _at(a)) and t >= cutoff_7d]

    by_kind: dict[str, int] = {}
    for a in actions:
        by_kind[str(a.get("kind") or "(unknown)")] = by_kind.get(str(a.get("kind") or "(unknown)"), 0) + 1
    shadow_count = sum(1 for a in actions if a.get("shadow"))
    live_count = len(actions) - shadow_count

    queue_by_status: dict[str, int] = {}
    for q in queue:
        queue_by_status[str(q.get("status") or "(unknown)")] = (
            queue_by_status.get(str(q.get("status") or "(unknown)"), 0) + 1
        )
    queue_by_channel: dict[str, int] = {}
    for q in queue:
        queue_by_channel[str(q.get("channel") or "(unknown)")] = (
            queue_by_channel.get(str(q.get("channel") or "(unknown)"), 0) + 1
        )

    # Mean time-to-approval over approved-with-acted-at rows
    deltas_min: list[float] = []
    for q in queue:
        if q.get("status") != "approved":
            continue
        created = _at(q)
        acted_raw = q.get("acted_at")
        if not isinstance(acted_raw, str) or not created:
            continue
        try:
            acted = dt.datetime.fromisoformat(acted_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        deltas_min.append((acted - created).total_seconds() / 60.0)
    mean_tta = f"{sum(deltas_min) / len(deltas_min):.1f} min" if deltas_min else "n/a"

    def _bar(label: str, value: int, total: int) -> str:
        pct = (value / total * 100.0) if total else 0.0
        width = int(round(pct * 2.4))  # 240 px when 100%
        return (
            f'<div class="bar"><span class="lbl">{_esc(label)}</span>'
            f'<span class="track"><span class="fill" style="width:{width}px"></span></span>'
            f'<span class="num">{value} ({pct:.0f}%)</span></div>'
        )

    total = len(actions) or 1
    kind_bars = "".join(_bar(k, v, total) for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    mode_bars = _bar("shadow", shadow_count, total) + _bar("live", live_count, total)
    queue_total = len(queue) or 1
    queue_status_bars = "".join(
        _bar(k, v, queue_total) for k, v in sorted(queue_by_status.items(), key=lambda kv: -kv[1])
    )
    queue_channel_bars = "".join(
        _bar(k, v, queue_total) for k, v in sorted(queue_by_channel.items(), key=lambda kv: -kv[1])
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>glossgo Salon Co-Pilot — stats</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; max-width: 980px; margin: 32px auto;
          padding: 0 24px; color: #1c1924; background: #faf8fb; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 14px; margin: 28px 0 12px; text-transform: uppercase;
        letter-spacing: 0.08em; color: #64596f; }}
  .meta {{ color: #64596f; margin-bottom: 24px; }}
  .nav a {{ color: #6f3aac; text-decoration: none; margin-right: 14px; }}
  .nav a:hover {{ text-decoration: underline; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
              margin: 20px 0; }}
  .kpi {{ background: #fff; padding: 16px; border-radius: 8px;
          box-shadow: 0 1px 3px rgba(20,5,40,.06); }}
  .kpi .label {{ color: #64596f; font-size: 11px; text-transform: uppercase;
                 letter-spacing: 0.06em; }}
  .kpi .val {{ font-size: 24px; font-weight: 600; color: #3c2b50; margin-top: 4px; }}
  .panel {{ background: #fff; padding: 16px 20px; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(20,5,40,.06); margin-bottom: 16px; }}
  .bar {{ display: grid; grid-template-columns: 130px 240px 1fr; gap: 12px;
          align-items: center; padding: 4px 0; font-size: 13px; }}
  .bar .lbl {{ color: #3c2b50; }}
  .bar .track {{ background: #ece4f1; border-radius: 4px; height: 14px;
                 overflow: hidden; }}
  .bar .fill {{ display: block; height: 100%; background: #6f3aac; border-radius: 4px; }}
  .bar .num {{ color: #64596f; font-variant-numeric: tabular-nums; }}
</style></head>
<body>
<h1>glossgo Salon Co-Pilot — stats</h1>
<p class="meta nav">
  <a href="/dashboard">← back to dashboard</a>
  Live aggregates from <code>copilot.agent_actions</code> + <code>copilot.owner_approval_queue</code>.
</p>

<div class="kpi-grid">
  <div class="kpi"><div class="label">Actions / 24 h</div><div class="val">{len(actions_24h)}</div></div>
  <div class="kpi"><div class="label">Actions / 7 d</div><div class="val">{len(actions_7d)}</div></div>
  <div class="kpi"><div class="label">Total actions</div><div class="val">{len(actions)}</div></div>
  <div class="kpi"><div class="label">Mean time to approval</div><div class="val">{mean_tta}</div></div>
</div>

<h2>Agent actions — by kind</h2>
<div class="panel">{kind_bars or '<i>no data</i>'}</div>

<h2>Agent actions — by mode (shadow / live)</h2>
<div class="panel">{mode_bars}</div>

<h2>Owner approval queue — by status</h2>
<div class="panel">{queue_status_bars or '<i>no data</i>'}</div>

<h2>Owner approval queue — by channel</h2>
<div class="panel">{queue_channel_bars or '<i>no data</i>'}</div>
</body></html>"""


@app.post("/dashboard/{approval_id}/approve")
async def approve(approval_id: str, request: Request) -> dict[str, object]:
    _require_dashboard_session(request)
    form = await request.form()
    _require_csrf(request, form.get("csrf"))
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

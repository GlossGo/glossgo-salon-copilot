"""HTTP entry point for the orchestrator (runs on Cloud Run).

Exposes two routes:
  POST /event    Body: {"type": "booking.cancelled", "business_id": "...", "booking_id": "..."}
                 -> runs the root agent on the event payload, returns the action log.
                 Requires `Authorization: Bearer <COPILOT_WEBHOOK_BEARER>` header.
  GET  /healthz  Liveness probe (unauthenticated).

In production this endpoint is fronted by a Pub/Sub push subscription that
forwards a Google-signed OIDC token; the bearer secret is a stopgap that
also covers manual curl runs from the demo + the Cloudflare Worker forwarder.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "agent": root_agent.name}


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

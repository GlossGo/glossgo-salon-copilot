"""HTTP entry point for the orchestrator (runs on Cloud Run).

Exposes two routes:
  POST /event    Body: {"type": "booking.cancelled", "business_id": "...", "booking_id": "..."}
                 -> runs the root agent on the event payload, returns the action log.
  GET  /healthz  Liveness probe.

In production this endpoint is fronted by a Pub/Sub push subscription; for the
hackathon demo we hit it directly with curl.
"""

from __future__ import annotations

import json
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from orchestrator.agent import root_agent

load_dotenv()

app = FastAPI(title="glossgo Salon Co-Pilot Orchestrator", version="0.1.0")
_runner = InMemoryRunner(agent=root_agent, app_name="glossgo-copilot")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "agent": root_agent.name}


@app.post("/event")
async def handle_event(request: Request) -> dict[str, object]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc

    event_type = payload.get("type")
    if not event_type:
        raise HTTPException(status_code=400, detail="missing 'type'")

    user_message = (
        f"A new salon event has arrived. Route it appropriately.\n\n"
        f"Event payload (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    session_id = payload.get("session_id") or f"evt-{uuid.uuid4().hex[:12]}"
    user_id = payload.get("business_id") or "system"

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

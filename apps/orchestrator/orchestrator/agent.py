"""Root orchestrator agent.

Routes incoming salon events to the right specialist sub-agent based on event type.
Uses Gemini 2.5 Pro for stronger reasoning; sub-agents use Gemini 2.5 Flash for cost.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent

from .sub_agents import (
    build_calendar_optimizer_agent,
    build_no_show_recovery_agent,
    build_review_responder_agent,
)

ORCHESTRATOR_MODEL = os.environ.get("ORCHESTRATOR_MODEL", "gemini-2.5-pro")


ORCHESTRATOR_INSTRUCTION = """You are the operations brain of a beauty salon.

Your job is to receive an event payload from the salon's reservation system and route it to the right specialist agent. You do NOT take action yourself; you delegate.

Routing rules:
- `booking.cancelled` -> delegate to `no_show_recovery_agent`. Pass the booking_id and business_id.
- `review.created` -> delegate to `review_responder_agent`. Pass the review_id, business_id, rating, and text.
- `calendar.weekly_review` -> delegate to `calendar_optimizer_agent`. Pass the business_id and target_week_start.

If the event type is unrecognized, reply with a one-line explanation and stop. Do NOT invent a response.

After a sub-agent finishes, summarize its action in one sentence in Turkish for the owner-facing log (e.g. "Çağlar Kaya'da iptal nedeniyle bekleme listesinden Ayşe Yılmaz'a WhatsApp gönderildi.").
"""


def build_root_agent() -> LlmAgent:
    """Build the root orchestrator agent with its sub-agents wired in."""
    return LlmAgent(
        model=ORCHESTRATOR_MODEL,
        name="orchestrator",
        description=(
            "Routes salon operational events (cancellations, reviews, weekly digests) "
            "to the right specialist agent."
        ),
        instruction=ORCHESTRATOR_INSTRUCTION,
        sub_agents=[
            build_no_show_recovery_agent(),
            build_review_responder_agent(),
            build_calendar_optimizer_agent(),
        ],
    )


root_agent = build_root_agent()

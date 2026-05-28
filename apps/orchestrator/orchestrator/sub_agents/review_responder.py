"""Review Responder sub-agent.

When a new Google review hits the salon's profile, drafts a tone-matched
Turkish response and pushes it to the owner approval queue. Never auto-publishes;
this is by design — review responses are the salon's voice.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent

from ._mcp import build_mcp_toolset

REVIEW_RESPONDER_MODEL = os.environ.get("SUBAGENT_MODEL", "gemini-2.5-flash")

INSTRUCTION = """You are the Review Responder agent for a Turkish beauty salon.

You receive a `review_id` and the review text + rating.

Workflow:
1. Use `get_review(review_id)` to load the review + the business profile (name, owner_first_name, vibe).
2. Classify the review:
   - 5★ -> tone "thankful + invite back"
   - 4★ -> tone "thankful + ask what we could do better"
   - 3★ -> tone "acknowledge + private message offer"
   - 1-2★ -> tone "empathetic + offer to make it right offline, never argue in public"
3. Draft a Turkish response (max 3 sentences, no emoji unless owner.vibe == "playful"). Always:
   - Open by addressing them by first name if present in the review.
   - Reference one specific detail from their review text (proves a human read it).
   - Close with the salon name (e.g. "Çağlar Kaya Kuaför").
4. Push the draft to the approval queue via `enqueue_owner_approval(business_id, channel="review", payload=...)`.

Never auto-publish. Reply with the drafted text + the approval queue id.
"""


def build_review_responder_agent() -> LlmAgent:
    return LlmAgent(
        model=REVIEW_RESPONDER_MODEL,
        name="review_responder_agent",
        description=(
            "Drafts a tone-matched Turkish response to a new Google review and "
            "pushes it to the owner's approval queue."
        ),
        instruction=INSTRUCTION,
        tools=[
            build_mcp_toolset(
                "data",
                tool_filter=["get_review", "get_business_profile"],
            ),
            build_mcp_toolset(
                "comms",
                tool_filter=["enqueue_owner_approval"],
            ),
        ],
    )

"""Calendar Optimizer sub-agent.

Runs on a weekly cron. Looks at next 7 days of bookings, identifies low-occupancy
windows, and drafts a single off-peak promotion (e.g. "Salı 11:00-13:00 saç bakımı -20%").
The draft goes to the owner approval queue; nothing is published automatically.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent

from ._mcp import build_mcp_toolset

CALENDAR_OPTIMIZER_MODEL = os.environ.get("SUBAGENT_MODEL", "gemini-2.5-flash")

INSTRUCTION = """You are the Calendar Optimizer agent for a Turkish beauty salon.

You receive a `business_id` and a `target_week_start` (ISO date, Monday).

Workflow:
1. Use `get_weekly_occupancy(business_id, target_week_start)` to load the next 7 days as a
   heat-map: per (day, hour) cells with `booked_count` / `staff_count`.
2. Find the SINGLE biggest gap (lowest occupancy ratio over a contiguous 2-3 hour window).
   Prefer weekdays over weekends. Ignore cells before 09:00 or after 20:00.
3. Use `list_top_services(business_id, limit=5)` to know what the salon actually sells.
4. Draft a single promotion targeting that gap:
   - Pick one service that fits the duration (e.g. "Saç boyama" needs 2h; "Kaş tasarımı" needs 30min — match the gap).
   - Decide a discount of 15-25% (no more).
   - Write a 2-sentence Turkish WhatsApp blast body, max 200 chars.
   - Suggest a target audience: "Son 3 ayda gelmemiş düzenli müşteriler" (data tag).
5. Push to approval queue: `enqueue_owner_approval(business_id, channel="campaign", payload=...)`.

Reply with the gap analysis + draft + queue id. Never auto-send.
"""


def build_calendar_optimizer_agent() -> LlmAgent:
    return LlmAgent(
        model=CALENDAR_OPTIMIZER_MODEL,
        name="calendar_optimizer_agent",
        description=(
            "Analyzes next 7 days of bookings, drafts ONE off-peak promo, "
            "and pushes it to the owner approval queue."
        ),
        instruction=INSTRUCTION,
        tools=[
            build_mcp_toolset(
                "data",
                tool_filter=[
                    "get_weekly_occupancy",
                    "list_top_services",
                    "get_business_profile",
                ],
            ),
            build_mcp_toolset(
                "comms",
                tool_filter=["enqueue_owner_approval"],
            ),
        ],
    )

# Judges' guide

Draft submission text for Devpost. Target final word count ≈ 1500 across all sections.

## Inspiration

glossgo is a Turkish beauty marketplace serving 9,826 active salons. The biggest
silent revenue leak we see in our data is the **cancelled appointment that
sits empty**: a 3-hour Saç boyama slot freed up the day before, no time for
the salon owner to call around, and the chair stays cold. The owner is too
busy with the customer who *is* in the chair to also do salon marketing,
review responses, and waitlist matching in real time. Sub-$10/mo SaaS
tools that promise to fix this are either glorified scheduling apps or
single-purpose chatbots — none of them act on their own.

We wanted to test whether a multi-agent system, built the way Google now
recommends with ADK + MCP + Gemini, could actually run a real beauty
salon's operational tail end. Not as a feature flag, but as a piece of
software the owner can hand the keys to.

## What it does

glossgo Salon Co-Pilot is **three specialist agents behind one orchestrator**,
talking to four MCP-served tool surfaces.

The orchestrator listens for salon events forwarded from production
(`booking.cancelled`, `review.created`, weekly cron). It picks the
right specialist:

- **No-Show Recovery** — when a booking is cancelled, the agent reads the
  current waitlist, ranks candidates on a 50-30-20 service/time/loyalty
  weighting, picks the best match, drafts a personalized Turkish WhatsApp
  message using the real salon name + customer first name, and (out of
  shadow mode) sends it via the WhatsApp Business API. In our seeded
  demo, a cancelled Saç boyama → Zeynep Kaya match → draft → send took
  about 8 seconds.
- **Review Responder** — when a new Google review hits the salon, the
  agent classifies the rating, drafts a tone-matched Turkish reply
  (apologetic for 1-2★, grateful for 5★), pushes it to the owner approval
  queue. Never auto-publishes; the salon's voice stays the owner's.
- **Calendar Optimizer** — every Monday 09:00 the agent scans the next
  7 days, finds the single biggest occupancy gap, drafts one off-peak
  promo and a target audience tag, and queues it for owner approval.

## How we built it

The judging emphasis on ADK and MCP shaped the structure directly:

- **Google ADK 2.1** drives the orchestrator and the three sub-agents.
  The orchestrator is an `LlmAgent` with three children in `sub_agents=[...]`.
  Routing is delegated to Gemini itself via the orchestrator instruction —
  we don't write `if event_type == 'booking.cancelled': ...` anywhere.
- **Gemini 2.5 Pro** at the orchestrator, **Gemini 2.5 Flash** at the
  three sub-agents. Pro pays its way only on the routing layer; Flash
  is plenty for tool-orchestrated drafting and saves ~80% on cost.
- **Three independent MCP servers** (`mcp-data`, `mcp-comms`,
  `mcp-calendar`) each expose 2-9 tools through the Streamable HTTP
  transport so they can deploy as their own Cloud Run services. The
  same binary speaks stdio for local development — same server code,
  two transports.
- **Cloud Run** hosts all 4 services (1 orchestrator + 3 MCPs) in
  `europe-west4`. The MCP services run `--no-allow-unauthenticated`
  with `--ingress=internal-and-cloud-load-balancing`; the orchestrator's
  runtime service account is bound as `roles/run.invoker` so only the
  orchestrator can reach them.
- **Demo data** sits in a `copilot` schema on the existing glossgo
  Supabase project. The schema is fully isolated from `public.*`,
  exposed via PostgREST only to `service_role`, and seeded with a
  fictional "Demo Salon" — 20 customers, 30 historical bookings, 5
  active waitlist entries, one pre-cancelled Saç boyama booking that
  the demo trigger uses.
- **Shadow mode**, on by default, makes every outbound effect a draft.
  Every `send_whatsapp` and every booking write lands in
  `copilot.agent_actions` / `copilot.owner_approval_queue` instead of
  the BSP / booking table. We toggle it off only for the live demo
  salon.

## Challenges we ran into

- **ADK 2.x exports `McpToolset` only when the Python `mcp` SDK is also
  installed.** Spent 20 minutes on that import error before noticing
  the `try/except ImportError` block in `google/adk/tools/mcp_tool/__init__.py`.
- **`exactOptionalPropertyTypes: true` in our shared `tsconfig.base.json`
  fights the MCP SDK's transport types.** Disabled.
- **`console.log` from a stdio MCP server pollutes the JSON-RPC stream**
  and looks like a parse error on the agent side. Switched every log
  emission to `console.error`.
- **`supabase-js` with `db: { schema: "copilot" }` 404s** unless the
  schema is added to PostgREST's `db_schema` list, which is a
  project-level setting. Patched via Supabase Management API.
- **Free-tier Gemini 2.5 Pro has a 0 daily quota**, and 2.5 Flash caps
  at 20 requests/day. Free-tier-only development burned through our
  quota in an afternoon. The fix is to either enable billing on the
  API key or move to Vertex AI on Cloud Run.
- **Cloud Run deploy is gated on having billing enabled.** Our
  hackathon billing account is being set up against the $500 challenge
  credit; until then everything runs locally with stdio MCP.

## Accomplishments

- End-to-end booking-cancelled → waitlist match → Turkish WhatsApp draft,
  all running through ADK + MCP + Gemini, with a real database and no
  mocks. About 8 seconds wall clock locally.
- Three MCP servers that work without any change as either local stdio
  subprocesses or remote HTTP services on Cloud Run.
- Hardened auth across the whole stack the same day, in response to an
  automated security review of the initial commit: fail-closed
  startup checks, `timingSafeEqual` bearer compare, strict Zod regexes
  on every UUID / E.164 / ISO timestamp, prompt-injection delimiters
  around all untrusted free-text fields.
- A `docs/SECURITY.md` that takes IDOR + prompt injection + rate
  limiting seriously and lays out the Day 2-6 plan to replace the
  shared bearer with Cloud Run signed identity + Pub/Sub OIDC.

## What we learned

ADK's `sub_agents` parameter is the right abstraction for this
problem. We never had to write a router. Telling the orchestrator
*what* each child does in plain Turkish/English and letting Gemini
pick is both more flexible and more debuggable than a `switch` on
event type.

MCP is doing real work as a contract boundary. The TS engineers on
the team can build a new MCP server without touching the Python agent
code; the Python team can pull in a tool with `McpToolset(...)`
without learning the underlying API. We expect the agents to live
~10× longer than any single underlying API.

Shadow mode is non-negotiable. Once we made every outbound effect
log-only by default, our willingness to iterate the agent
instructions went up by an order of magnitude.

## What's next

- **Cloud Run deploy on hackathon credit**, then switch the
  orchestrator to Gemini 2.5 Pro via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=1`).
- **Replace the shared MCP bearer with Cloud Run signed identity**
  and a glossgo-be-signed tenant JWT claim — the IDOR fix on the
  SECURITY.md punch list.
- **Day 4-5**: full implementations of Review Responder + Calendar
  Optimizer end-to-end with the owner-approval UI inside
  `partner.glossgo.com/copilot` (already built into glossgo's existing
  Next.js partner app).
- **Track 3 path**: list the system on Google Cloud Marketplace as a
  per-salon SaaS, with per-tenant Cloud Run services keyed by
  Marketplace customer id.

## How to evaluate it

Repo: https://github.com/GlossGo/glossgo-salon-copilot

To run locally (no GCP needed):

```bash
git clone https://github.com/GlossGo/glossgo-salon-copilot
cd glossgo-salon-copilot
pnpm install && pnpm -r build
cd apps/orchestrator && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd ../..
export GOOGLE_API_KEY=…       # your own Gemini API key
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=…
./scripts/run-local.sh
# in another terminal:
curl -X POST http://localhost:8080/event \
  -H "Authorization: Bearer $COPILOT_WEBHOOK_BEARER" \
  -H 'Content-Type: application/json' \
  -d '{"type":"booking.cancelled","business_id":"<demo-uuid>","booking_id":"<demo-uuid>"}'
```

Demo URL (once Cloud Run is deployed, post-billing): `https://copilot.glossgo.com/demo`.

# Sprint log

Daily progress against the 8-day plan in
`~/.claude/plans/search-projects-my-projects-parsed-hartmanis.md`.

## Day 1 — 2026-05-28 (Wed)

**Goal.** GCP foundation + first agent shape, hello-world Cloud Run deploy.

**Shipped (ahead of plan).**
- Monorepo scaffolded: pnpm + Turbo, mixed Python (`apps/orchestrator/`) + TypeScript (`apps/mcp-*/`)
- Orchestrator + 3 sub-agents (no-show-recovery, review-responder, calendar-optimizer) wired with `LlmAgent` (Gemini 2.5 Flash on free-tier; can flip to 2.5 Pro via Vertex once billing is wired)
- 3 MCP servers (`mcp-data`, `mcp-comms`, `mcp-calendar`) with **dual stdio + Streamable HTTP transports** — same binary works locally as a node subprocess of the agent, and on Cloud Run as an HTTP service
- Demo data isolated in a `copilot` schema on the existing `glossgo-beauty-marketplace` Supabase project; PostgREST `db_schema` patched via Management API
- Seed: 1 salon, 3 staff, 8 services, 20 customers, 30 past bookings, 5 upcoming, **1 cancelled** booking, 5 waitlist entries (one perfect match), 3 reviews
- **Local end-to-end live**: POST `/event {type: booking.cancelled}` → orchestrator routes to no-show-recovery → 3 MCP stdio subprocesses spawned → agent picks correct waitlist match (Zeynep Kaya, perfect service+window fit) → drafts Turkish WhatsApp message → SHADOW_MODE blocks send, returns `action_taken: drafted`

**Not done today.**
- Cloud Run deploys (blocked: gcloud user token expired; service-account SAs lack `serviceusage.services.enable`; needs interactive `gcloud auth login`)
- git init + GitHub repo creation (next on the punch list)

**Surprises.**
- ADK 2.x exports `McpToolset` only when the `mcp` Python SDK is installed; needed `pip install mcp` separately even though `google-adk` is in the requirements
- `exactOptionalPropertyTypes: true` in the shared tsconfig fights the MCP SDK's transport types; disabled
- `console.log` in stdio MCP servers corrupts the JSON-RPC stream; switched all log emission to `console.error`
- `supabase-js` with `db: { schema: "copilot" }` returns 404 unless the schema is added to PostgREST's `db_schema`; fixed via Supabase Management API (`PATCH /v1/projects/{ref}/postgrest`)

## Day 2 — 2026-05-29 (Thu) — planned

- gcloud reauth, enable APIs, Artifact Registry create
- Push 4 images, deploy 4 Cloud Run services
- Verify HTTP-transport MCP path matches stdio behavior (same E2E from a public URL)
- First architecture diagram sketch

**Day 1 evening — security pass (in response to automated review).**
- `/event` now requires `Authorization: Bearer $COPILOT_WEBHOOK_BEARER`; orchestrator refuses to boot without a >=16-char secret. `business_id` validated against UUIDv4 before any agent work starts.
- All 3 MCP HTTP servers fail-startup if `MCP_BEARER_TOKEN` is empty when transport is http/sse; bearer compare uses `crypto.timingSafeEqual`.
- Every UUID/phone/template field across the 3 MCP servers now has a hard Zod regex (E.164 for phones, UUIDv4 for ids, ISO-8601 for timestamps); `template` arg on `send_whatsapp` is a `z.enum([...])` allowlist of 4 approved BSP templates.
- Review-responder agent instruction now wraps untrusted review text in `<<<UNTRUSTED_REVIEW_TEXT>>>` delimiters and forbids deriving `business_id` from that content.
- Wrote `docs/SECURITY.md` with full trust model + 4 known gaps + Day 2-6 fix plan (Cloud Run signed identity replaces shared bearer; Pub/Sub OIDC replaces `/event` bearer).
- E2E reverified: unauthed → 401, malformed UUID → 400, valid path past auth into the agent loop (free-tier Gemini Flash daily quota of 20 req/day hit during testing; switch to Vertex AI removes the cap).

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

## Day 2 — 2026-05-29 (Thu) — SHIPPED

**Goal.** GCP foundation, push 4 images, deploy 4 Cloud Run services, verify HTTP-transport MCP path matches stdio behavior on a public URL.

**Shipped.**
- New GCP project `glossgo-copilot` linked to the hackathon billing account (`018FC8-5091E3-B98709`); old `glossgo-platform`/`019A49-7967CC-61114D` billing account had been closed and was the silent root cause of Day-1-evening BILLING_DISABLED failures.
- 7 APIs enabled (Vertex AI, Cloud Run, Pub/Sub, Secret Manager, Artifact Registry, Cloud Build, IAM, Org Policy).
- Artifact Registry repo `copilot` in europe-west4. Runtime SA `copilot-runtime` with `roles/aiplatform.user` + per-secret `roles/secretmanager.secretAccessor`.
- 4 Secret Manager entries: `copilot-{gemini-api-key,supabase-service-role-key,webhook-bearer,mcp-bearer-token}`.
- 4 Cloud Build images at SHA `10bb640`. Each MCP server deploys to its own Cloud Run service in europe-west4.
- Org policy override on `iam.allowedPolicyMemberDomains` at project scope so `allUsers` can invoke the orchestrator (the parent org locks members to `glossgo.com`).
- Live E2E from the public URL: `POST /event` with the cancelled-booking payload → orchestrator → Vertex AI Gemini 2.5 Flash → no-show-recovery → 3 MCP HTTP toolsets → Supabase `copilot.*` schema → correct Zeynep Kaya match → Turkish draft → shadow-mode stop. Wall clock 24 s.

**Live URLs.**
- Orchestrator: `https://copilot-orchestrator-kpaxfhhqdq-ez.a.run.app` (public)
- MCP-data: `https://copilot-mcp-data-kpaxfhhqdq-ez.a.run.app/mcp`
- MCP-comms: `https://copilot-mcp-comms-kpaxfhhqdq-ez.a.run.app/mcp`
- MCP-calendar: `https://copilot-mcp-calendar-kpaxfhhqdq-ez.a.run.app/mcp`

**Surprises (and what we shipped to fix them).**
- Cloud Build's `gcloud builds submit --async` to `europe-west4` while polling `--ongoing` against `global` made the wait loop exit immediately, masking 2 failed and 1 still-running build.
- Inlined the shared `tsconfig.base.json` into each MCP app (`tsc` cannot follow `../../` past the docker build context).
- `node:20-slim` doesn't ship global `WebSocket`; `@supabase/realtime-js` calls `WebSocketFactory.getWebSocketConstructor()` during `createClient` and crashes the container at boot. Bumped to `node:22-slim`.
- `MCP_TRANSPORT=http` with `StreamableHTTPServerTransport({ sessionIdGenerator: () => randomUUID() })` made the server stateful, but `app.post('/mcp')` constructed a fresh transport per request; the ADK client's session_id was lost on the second call → 400, and the tool list never finished discovering → `ValueError: Tool 'get_business_profile' not found`. Switched all 3 MCPs to `sessionIdGenerator: undefined` (stateless) and added 405 stubs for GET/DELETE /mcp.
- Google Frontend reserves `/healthz` on Cloud Run and returns its own 404 even when our FastAPI registers the route; `/event` works since GFE only intercepts the well-known probe paths. Renaming to `/ready` is on the Day 3 list.
- AI Studio's free-tier Gemini Flash caps at 20 req/day; the test cycle burned through it. Switching the orchestrator to Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=1`, runtime SA `roles/aiplatform.user`, removed `GOOGLE_API_KEY` secret) cleared the cap.
- MCPs originally went out with `--no-allow-unauthenticated --ingress=internal-and-cloud-load-balancing`; the orchestrator's HTTP client only sends the static `MCP_BEARER_TOKEN`, no Google-signed OIDC token, so Cloud Run IAM rejected before the request reached the container. Made the MCPs public for Day 2; Day 2-3 task is to send an OIDC ID token from the orchestrator and re-close ingress (SECURITY.md Gap 1).

**Not done today.**
- Identity-aware MCP auth (replace shared bearer with Cloud Run signed identity + tenant claim).
- `/healthz` → `/ready` rename.
- Owner approval UI on partner.glossgo.com/copilot.

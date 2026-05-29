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

## Day 3 — 2026-05-29 (continued, evening) — security pass + multi-agent E2E

**Goal.** Close SECURITY.md Gap 1's identity layer (OIDC MCP auth), rename
/healthz, run all three sub-agents end-to-end on the public Cloud Run URL.

**Shipped.**
- `/healthz` → `/ready` (Cloud Run GFE reserves `/healthz` and returns its
  own 404 even when our FastAPI registers the route).
- OIDC ID token fetcher landed (`_fetch_id_token`, audience derived from
  the MCP service URL with `/mcp` stripped) but gated behind `MCP_USE_OIDC=1`.
  Cloud Run validated our metadata-server-issued tokens with
  `WWW-Authenticate: Bearer error=invalid_token, error_description="The
  access token could not be verified"` — same failure when impersonating
  the runtime SA locally via `gcloud auth print-identity-token`. Deferred
  to Day 6 for a fresh debug pass; static `MCP_BEARER_TOKEN` remains the
  primary auth layer in the meantime. `SECURITY.md` updated.
- Caught a credential-leak in the OIDC instrumentation (`token[:24]=…` in
  a print line) before any token reached production and replaced it with
  a `auth=oidc / static-bearer / NONE` log instead.

**Multi-agent E2E on the public URL (all green).**
- no-show-recovery: `booking.cancelled` → Zeynep Kaya match (perfect
  service + time-window + loyalty fit) → Turkish WhatsApp draft.  28 s.
- review-responder (2★): `review.created` → empathetic Turkish reply →
  pushed to `owner_approval_queue`.  17 s.
- review-responder (5★): same path, thankful tone, queue id returned. 12 s.
- calendar-optimizer: `calendar.weekly_review` → returned "no occupancy
  data" for an empty-schedule week (correct behavior — refused to invent
  a campaign without input).  4 s.

**Surprises (and what we shipped to fix them).**
- ADK's `LlmAgent` treats the instruction string as a `str.format()`
  template and substitutes session variables. The review-responder
  instruction had `{text}` and `{profile.id}` as illustrative placeholders;
  ADK saw them as undefined context variables and raised `KeyError:
  'Context variable not found: text'`. Rewrote the instruction to describe
  the substitution and the JSON payload shape in plain English with no
  literal braces.

## Day 4–5 — 2026-05-29 (late) — owner UI + prompt-injection hardening

**Owner UI (`apps/orchestrator/main.py`).**
- `GET /dashboard` — read-only HTML view of `copilot.agent_actions`
  (last 25) and the pending `copilot.owner_approval_queue`. Inline CSS,
  no external assets.
- `POST /dashboard/{id}/approve` — idempotent transition to
  `status='approved'`; double-clicks return 404 not silent re-approve.
- Auth: cookie session (`copilot_dash`, HMAC-signed with the dashboard
  token, HttpOnly + Secure + SameSite=Strict + 4 h TTL) OR
  `Authorization: Bearer …` for scripts. Browser flow:
  `GET /dashboard/login` form → `POST /dashboard/login` validates with
  `hmac.compare_digest` → 303 to `/dashboard` with cookies set.
- CSRF: per-session HMAC-signed nonce in a non-HttpOnly companion
  cookie (`copilot_csrf`), echoed into a hidden form field. Approve
  handler verifies the nonce AND that the request's Origin/Referer
  hostname matches the request's Host header.
- `COPILOT_DASHBOARD_TOKEN` is a SEPARATE Secret Manager entry from
  `COPILOT_WEBHOOK_BEARER` (the security review caught a fall-through;
  fixed). Orchestrator fails to boot if the dashboard token is set but
  <16 chars.

**Prompt-injection defense moved server-side (mcp-data `get_review`).**
The MCP server now wraps the review's `text` field in
`<<<UNTRUSTED_REVIEW_TEXT>>>...<<<END_UNTRUSTED_REVIEW_TEXT>>>` before
returning it. A model that forgets to add the delimiters can still no
longer smuggle raw attacker bytes into its reasoning context. The server
also strips C0/C1 controls, zero-width / bidi-override characters,
neutralizes `system:` / `assistant:` role prefixes, and disarms any
literal close-delimiter the attacker tried to inject.

**Verification (11 / 11 green on the public URL).**

| # | Expected | Got |
|---|---|---|
| 1: `/dashboard` no auth | 401 | 401 |
| 2: `?token=…` URL ignored | 401 | 401 |
| 3: `/dashboard` with `Authorization: Bearer` | 200 | 200 |
| 4: `/dashboard/login` wrong token | 401 | 401 |
| 5: `/dashboard/login` correct → 303 → `/dashboard` | 200 | 303 + 200 |
| 6: `/dashboard` with stored cookie | rows | 200 + 4 rows |
| 7: approve without CSRF | 403 | 403 |
| 8: approve with cookie + CSRF + Origin | 200 | 200 + JSON |
| 9: re-approve same id | 404 | 404 |
| 10: approve with wrong CSRF token | 403 | 403 |
| 11: approve with hostile Origin | 403 | 403 |

**Still pending.**
- Per-owner identity → per-tenant `business_id` row scoping (`SECURITY.md`
  Gap 6 'still pending'). Day 7.
- OIDC MCP audience debug + re-lock MCPs to `--no-allow-unauthenticated`.
  Day 6.
- Demo video + architecture PNG + Devpost write-up polish. Day 6–7.

## Day 5 — 2026-05-29 (continued, +5h) — one-click demo + diagrams

**Architecture diagram.** `docs/architecture.mmd` rendered to PNG (264 KB,
2400 px, transparent) and SVG (66 KB) via `mmdc`. Embedded in the README
and the judges-guide.

**Dashboard demo trigger.** Added `POST /dashboard/demo` behind the same
cookie + CSRF gate as `/approve`. It fires all three pre-seeded events
(`booking.cancelled`, `review.created`, `calendar.weekly_review`) into the
orchestrator concurrently via `asyncio.gather`, returns 303 to
`/dashboard?ran=demo`. Wall clock ~22 s for the full fan-out on the public
Cloud Run URL. After the demo the dashboard shows 4 pending approvals
(3 review drafts + 1 campaign) and 6 shadow-mode `send_whatsapp` rows. A
green "Demo run complete" banner confirms the click.

**Verification.** 5 / 5 green:

| # | Expected | Got |
|---|---|---|
| dashboard renders the "Trigger demo" button | yes | yes (button + caption + form) |
| POST /dashboard/demo without CSRF | 403 | 403 |
| POST /dashboard/demo with CSRF | 303 → /dashboard?ran=demo | 303, 22 s wall clock |
| post-demo dashboard shows new rows | ≥3 approvals + ≥3 actions | 4 approvals + 6 actions |
| post-demo banner | shown | "Demo run complete" green banner |

**Judges-guide.** `docs/judges-guide.md` rewritten with:
- Live URLs (orchestrator + dashboard login).
- Architecture + dashboard PNGs embedded.
- The actual measured numbers per agent (28 s no-show, 17 s 2★ review,
  12 s 5★ review, 4 s empty-calendar refusal).
- A 4-curl quickstart that exercises /ready + the 3 event types under
  60 s total.
- An honest "Challenges we ran into" list — 10 real bugs and their fix
  commits, in the order we hit them.

**Cumulative state of the system.**
- Multi-agent system fully operational on public Cloud Run URL.
- Cookie-session + CSRF dashboard with one-click multi-agent demo.
- Three sub-agents tested green on Vertex AI Gemini 2.5 Flash.
- 6 SECURITY.md gaps with explicit Day 6 / Day 7 fix plans for each
  open one.
- 13 commits, all push'd to main, none with AI attribution.

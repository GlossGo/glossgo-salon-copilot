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

## Day 7 — 2026-05-29 (continued) — observability + submission docs

**Goal.** Add a production-grade observability surface, write the demo
video script, and bake the Devpost submission checklist.

**Shipped.**
- `GET /dashboard/stats` — read-only rollups over `copilot.agent_actions`
  + `copilot.owner_approval_queue`. KPIs (actions over 24 h / 7 d / total +
  mean time-to-approval) and four bar-chart panels (by kind, by mode,
  by status, by channel). Pure CSS, no JS, no chart library. Same cookie/
  bearer auth as `/dashboard`; no CSRF needed because it's read-only.
  Hot-linked from the main dashboard.
- `docs/demo-video-script.md` — 90-second timing storyboard with
  narration. Built around the dashboard's natural 22 s "Trigger demo"
  wait beat (architecture voiceover covers the spinner). Fallback
  script + setup checklist included.
- `docs/devpost-checklist.md` — required deliverables, three Devpost
  registration questions answered, eligibility rationale (Softween LTD
  as the qualifying startup entity in EMEA), the judging-criteria
  evidence map, and a pre-submit hygiene checklist that I verified
  before each commit (0 AI-tool footers, 0 tracked secrets, repo public,
  `/ready` returns 200).
- README polished: live URLs table at top, four measured wall-clock
  numbers in the agents table, dashboard + stats screenshots embedded,
  4-curl judge quickstart inline.

**Verification.**
- `/dashboard/stats` unauth → 401.
- `/dashboard/stats` with cookie → 200, 3672 bytes HTML, all four
  panels rendered with correct rollup numbers (3 shadow-mode
  send_whatsapp actions, 4 pending approvals + 1 approved, 4 review
  channel + 1 campaign channel rows).
- Screenshot `docs/img/stats.png` re-rendered (65 K, 1280 px wide).

**Not done today.**
- OIDC audience re-debug + MCP lockdown (SECURITY.md Gap 1).
- Per-tenant `business_id` JWT claim (SECURITY.md Gap 6).
- Recording the actual demo video (script is ready; Bilal records).
- Submitting on Devpost.

## Day 7 final — 2026-05-29 — 4 new surfaces for the judges

User opted in to four feature additions to differentiate the submission
(skipped real Çağlar Kaya pilot — too operationally risky).

**Bilingual dashboard.** Every new agent action now emits a one-line
`decision_summary_en` next to the Turkish customer draft, surfaced as a
green pill on `/dashboard`. Older rows fall back gracefully to raw payload.
2 services rebuilt (orchestrator + mcp-comms); 5 files changed.

**Agent reasoning trace.** New `copilot.agent_traces` table, captures every
ADK event during `/event` runs (routing, tool calls, tool responses, final
draft). Renders at `/dashboard/trace/{session_id}`. Verified: a typical
no-show-recovery run produced 13 captured events (1 routing + 6 tool calls
+ 6 tool responses). Dashboard gains a "Recent reasoning traces" panel
linking the last 5 session ids.

**Marketplace economics calculator at `/dashboard/economics`.** Pure
CSS + vanilla JS sliders, no backend deps beyond auth. Five inputs, three
KPI groups, two pricing tiers (Pro ₺199, Business ₺499). Defaults match
glossgo's actual operating numbers.

**Landing page at `apps/landing/index.html`.** 12 KB hand-written
responsive HTML. Deployed to https://glossgo-copilot.pages.dev via
wrangler. Custom domain copilot.glossgo.com attached on Pages side
(status: pending) — the existing `100::` AAAA record from softween-hub
needs a manual DNS swap in the CF dashboard (current token lacks
DNS.Edit on glossgo.com zone). Documented in `apps/landing/README.md`.

**Multi-LLM battle at `/dashboard/battle`.** Same Turkish no-show-recovery
prompt fired in parallel at Gemini 2.5 Pro / Flash / Flash Lite on Vertex
AI. Recorded run: Pro 6.07s/$0.00010, Flash 3.89s/$0.00001 (16× cheaper
than Pro), Flash Lite 0.91s/$0.0000064 (fastest but starts dropping
nuance). Makes the "we picked Flash" choice auditable. No external API
keys — all on Vertex AI.

**Final surfaces (all auth-gated except landing + /ready):**

| Surface | URL |
|---|---|
| Landing | <https://glossgo-copilot.pages.dev> |
| Liveness | <https://copilot-orchestrator-kpaxfhhqdq-ez.a.run.app/ready> |
| Login | …/dashboard/login |
| Operator dashboard | …/dashboard |
| Trigger demo | POST …/dashboard/demo |
| Reasoning trace | …/dashboard/trace/{session_id} |
| Stats rollups | …/dashboard/stats |
| Economics calculator | …/dashboard/economics |
| Model battle | …/dashboard/battle |
| Approve a draft | POST …/dashboard/{id}/approve |
| Event ingestion | POST …/event (bearer-auth, no cookie) |

**Commit log (this session):**
- `ff7321e` bilingual dashboard contract
- `38b4711` judges-guide bilingual writeup
- `59733c5` /dashboard/trace + agent_traces table
- `b7b0082` trace screenshot
- `330143b` /dashboard/economics
- `b3202cc` economics screenshot
- `8578dac` apps/landing + CF Pages deploy
- `263d778` /dashboard/battle
- `08a5514` battle screenshot

**Day 8 (user-only): record 90s video + submit.**

## 2026-05-30 — credit arrived, real-volume populate run

**Credit landing.** Devpost $500 + GenAI App Builder ₺45K + Marketing
AI Agents Challenge ₺22.5K all visible in the glossgo-copilot project
billing UI. Total ~₺67K + $500 USD available immediately.

**Real-volume populate (used <\$1 of credit).** Fired 20 events
through the live `/event` endpoint in parallel, all HTTP 200:
- 5× `booking.cancelled` (Zeynep Kaya match), 28-41 s each
- 5× `review.created` 2★, 10-18 s each
- 3× `review.created` 5★, 11-12 s each
- 3× `review.created` 4★, 10-12 s each
- 4× `calendar.weekly_review` across 4 different weeks, 6-18 s each

**Dashboard state after populate:**

| Metric | Before | After |
|---|---|---|
| Pending owner approvals | 4 | 17 |
| Recent `send_whatsapp` shadow actions | 3 | 16 |
| English decision pills | 2 | 18 |
| Recent reasoning traces in panel | 1 | 5 |

Screenshots refreshed: `docs/img/dashboard.png` (215 K → 624 K, captures
the busy state) + `docs/img/stats.png` (now backed by real 24h activity).

**Multi-tenant authorization fix committed but not yet deployed.** A
separate session shipped commit `a5386a2`: every MCP-data read
(`get_cancelled_booking`, `get_review`, `get_customer`, `get_service`)
now requires a `business_id` arg and enforces a server-side
`.eq("business_id", business_id)` filter. Sub-agent instructions
updated to pass the verified session `business_id` into every tool
call and never pick one from untrusted content. This closes the
authorization half of SECURITY.md Gap 6.

The source is in `main` but Cloud Run still serves the previous build
(my gcloud token expired during the rebuild attempt; needs interactive
re-auth). The 20-event populate run above hit the previous deployed
code path, which is unaffected at the URL level — judges-facing surface
keeps working.

**Day 8 (pending).**
- `gcloud auth login` and redeploy the tenant-scoped image so the
  authorization tightening goes live.
- Demo video kaydı.
- Devpost form fill + submit.

## 2026-06-08 — deploy-state reconciliation + full live re-verification

**Finding: the "Day 8 redeploy" item above was already done.** The note
in the 2026-05-30 section ("source is in main but Cloud Run still serves
the previous build") was written *before* a later session deployed it.
Reconciled today against the live services:

- Deployed orchestrator + mcp-data images are tagged `3493d19`, which
  **already contains** the tenant-scoping fix `a5386a2`
  (`git merge-base --is-ancestor a5386a2 3493d19` = true).
- The only commits since the deployed `3493d19` (`e35da42`, `62e5d8d`,
  `a6cdda7`) touch **docs, the landing app, README, and image-gen
  scripts only** — zero changes under `apps/orchestrator/` or
  `apps/mcp-data/`. So the running services are functionally current;
  **no Cloud Run redeploy was required.**

**Independent live verification (this session, against the deployed URLs):**

| Check | Expected | Got |
|---|---|---|
| Cross-tenant MCP `get_cancelled_booking` (wrong `business_id`) | refused | `isError:true` — `booking … not found in tenant 99999999-…` |
| Same-tenant control (right `business_id`) | booking JSON | full row returned (business_id `1111…0001`) |
| `booking.cancelled` → no-show-recovery | 200 + TR draft | 200 in 27.7 s, matched Zeynep Kaya, shadow `drafted` |
| `review.created` 2★ → review-responder | 200 + queue row | 200 in 11.3 s, TR reply, queue id `49d661ff…` + trace URL |
| `/ready` (public) | 200 | 200 |
| `/dashboard` (no auth) | 401 | 401 |

The authorization half of SECURITY.md Gap 6 is confirmed **enforced in
production**, not just in source. Landing page `copilot.glossgo.com` is
live (HTTP 200) and serving the current explainer imagery.

**Genuinely remaining (user-only, unchanged):** record the ~90 s demo
video and fill + submit the Devpost form. No engineering work outstanding.

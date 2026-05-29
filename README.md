# glossgo Salon Co-Pilot

> Autonomous multi-agent system that runs a beauty salon's marketing + operations while the owner sleeps.
> **Submission for the Google for Startups AI Agents Challenge, Track 1 (Build).**

## What it does

When something happens at a salon (a customer cancels, a Google review drops, the next week is suddenly empty), an orchestrator agent routes the event to a specialist sub-agent that takes autonomous action via Model Context Protocol (MCP) tools.

| Trigger | Sub-agent | Action |
|---|---|---|
| `booking.cancelled` | No-Show Recovery | Pick best waitlist match, draft personalized WhatsApp, send, handle reply, create booking |
| `review.created` (Google) | Review Responder | Draft tone-matched Turkish response, push to owner approval queue |
| Weekly cron | Calendar Optimizer | Analyze empty slots, draft off-peak promo, push campaign draft for approval |

## Stack

- **Agent framework**: [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) — Python
- **Foundation model**: Gemini 2.5 Pro (orchestrator) + Gemini 2.5 Flash (sub-agents)
- **Tool protocol**: 3 standalone [Model Context Protocol](https://modelcontextprotocol.io/) servers (TypeScript)
- **Hosting**: Cloud Run (each agent + each MCP server is its own service)
- **Trigger bus**: Cloudflare Worker webhook → Google Pub/Sub → ADK orchestrator
- **Database**: Existing glossgo production Supabase (read-only via MCP)
- **Observability**: Vertex AI Agent Engine traces + PostHog `$ai_generation` events

## Architecture

![architecture](docs/img/architecture.png)

Source: [`docs/architecture.mmd`](docs/architecture.mmd). Re-render with
`npx -p @mermaid-js/mermaid-cli mmdc -i docs/architecture.mmd -o docs/img/architecture.png -b transparent -w 2400 -t neutral`.

The diagram shows the target architecture. Today's deployment matches it
except for one temporary relaxation called out in
[`docs/SECURITY.md`](docs/SECURITY.md) Gap 1: MCP services run with
`--ingress=all` and `allUsers` as `run.invoker` while the OIDC audience
validation is debugged. The container-level static bearer
(`MCP_BEARER_TOKEN`) is the actual auth gate today; Day 6 swaps it for
Cloud Run signed identity + re-locks the ingress.

## Repo layout

```
apps/
  orchestrator/             # ADK root agent (Python, Gemini 2.5 Pro)
  agent-no-show-recovery/   # ADK sub-agent (Python, Gemini 2.5 Flash)
  agent-review-responder/   # ADK sub-agent
  agent-calendar-optimizer/ # ADK sub-agent
  mcp-data/                 # MCP server: Supabase read (TypeScript)
  mcp-comms/                # MCP server: WhatsApp send (TypeScript)
  mcp-calendar/             # MCP server: booking write (TypeScript)
packages/
  shared/                   # Shared types + prompts + eval harness
infra/
  cloudrun/                 # service.yaml per service
scripts/
  seed-demo-salon.ts        # Day-1 demo data seed
docs/
  architecture.md
  judges-guide.md
```

## Quick start

```bash
pnpm install
pnpm -r build
pnpm dev                    # Boot all 7 services locally

# In another terminal, trigger an event:
curl -X POST localhost:8080/event \
  -H 'Content-Type: application/json' \
  -d '{"type":"booking.cancelled","booking_id":"demo-bk-001"}'
```

## Cloud deploy

```bash
./scripts/deploy-cloudrun.sh    # uses PROJECT=glossgo-copilot, REGION=europe-west4
```

Full deploy walkthrough (one-time prerequisites + redeploy loop):
[`docs/deploy.md`](docs/deploy.md). Trust model + auth controls:
[`docs/SECURITY.md`](docs/SECURITY.md). Architecture diagram source:
[`docs/architecture.mmd`](docs/architecture.mmd).

## Status

Active development. See [`docs/sprint-log.md`](docs/sprint-log.md) for daily progress.

## License

MIT (see [LICENSE](LICENSE))

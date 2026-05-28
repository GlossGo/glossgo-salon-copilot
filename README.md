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

```
Cloudflare Worker (existing glossgo-be)
        |
        | event (booking.cancelled, review.created, ...)
        v
   Pub/Sub topic: copilot-events
        |
        v
   Orchestrator Agent (Cloud Run, Gemini 2.5 Pro)
        |
        +--routes-to--> No-Show Recovery (Gemini Flash)
        |                    |
        |                    +--uses--> mcp-data (Supabase read)
        |                    +--uses--> mcp-comms (WhatsApp send)
        |                    +--uses--> mcp-calendar (booking write)
        |
        +--routes-to--> Review Responder (Gemini Flash)
        |
        +--routes-to--> Calendar Optimizer (Gemini Flash)
```

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

## Status

Active development. See [`docs/sprint-log.md`](docs/sprint-log.md) for daily progress.

## License

MIT (see [LICENSE](LICENSE))

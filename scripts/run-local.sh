#!/usr/bin/env bash
# Pull secrets from Doppler and run the orchestrator locally with stdio MCP.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/apps/orchestrator"

if [[ ! -d .venv ]]; then
  echo "==> creating venv"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt --quiet
else
  source .venv/bin/activate
fi

export GOOGLE_API_KEY="$(doppler secrets get GEMINI_API_KEY --project glossgo --config prd --plain)"
export GOOGLE_GENAI_USE_VERTEXAI=0
export SUPABASE_URL="https://rpaaxlifkpgytiziyawq.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="$(doppler secrets get SUPABASE_SERVICE_ROLE_KEY --project glossgo --config prd --plain)"
export MCP_TRANSPORT=stdio
export COPILOT_REPO_ROOT="$REPO_ROOT"
export ORCHESTRATOR_MODEL="${ORCHESTRATOR_MODEL:-gemini-2.5-pro}"
export SUBAGENT_MODEL="${SUBAGENT_MODEL:-gemini-2.5-flash}"
export SHADOW_MODE="${SHADOW_MODE:-true}"
export PORT="${PORT:-8080}"

# /event is auth-gated; generate a stable per-shell secret unless caller set one.
# Print it to the console so you can curl with the right header.
if [[ -z "${COPILOT_WEBHOOK_BEARER:-}" ]]; then
  export COPILOT_WEBHOOK_BEARER="$(openssl rand -hex 32)"
fi

cat <<INFO
==> orchestrator on :$PORT  (model=$ORCHESTRATOR_MODEL, transport=$MCP_TRANSPORT, shadow=$SHADOW_MODE)
    Webhook bearer: $COPILOT_WEBHOOK_BEARER
    Smoke test:
      curl -X POST http://localhost:$PORT/event \\
        -H "Authorization: Bearer \$COPILOT_WEBHOOK_BEARER" \\
        -H "Content-Type: application/json" \\
        -d '{"type":"booking.cancelled","business_id":"11111111-0000-0000-0000-000000000001","booking_id":"55555555-0000-0000-0000-000000000001"}'
INFO

exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT"

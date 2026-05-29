#!/usr/bin/env bash
# Deploy the 4 services to Cloud Run after Cloud Build finishes.
# Idempotent: rerun on each git push.
set -euo pipefail

PROJECT="${PROJECT:-glossgo-copilot}"
REGION="${REGION:-europe-west4}"
SHA="${SHA:-$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --short HEAD)}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT}/copilot"
SA="copilot-runtime@${PROJECT}.iam.gserviceaccount.com"

SUPABASE_URL_VAL="https://rpaaxlifkpgytiziyawq.supabase.co"

deploy_mcp() {
  local NAME=$1 PORT=$2
  echo "==> deploying $NAME at SHA $SHA"
  gcloud run deploy "copilot-$NAME" \
    --image "$REGISTRY/$NAME:$SHA" \
    --project "$PROJECT" --region "$REGION" \
    --service-account "$SA" \
    --no-allow-unauthenticated \
    --ingress internal-and-cloud-load-balancing \
    --port "$PORT" \
    --memory 512Mi --cpu 1 \
    --max-instances 5 --concurrency 40 --timeout 60 \
    --set-env-vars "SUPABASE_URL=$SUPABASE_URL_VAL,MCP_TRANSPORT=http,SHADOW_MODE=true" \
    --set-secrets "SUPABASE_SERVICE_ROLE_KEY=copilot-supabase-service-role-key:latest,MCP_BEARER_TOKEN=copilot-mcp-bearer-token:latest" \
    --quiet 2>&1 | tail -3
}

deploy_mcp mcp-data     8081
deploy_mcp mcp-comms    8082
deploy_mcp mcp-calendar 8083

# Resolve MCP URLs (append /mcp to each)
MCP_DATA_URL="$(gcloud run services describe copilot-mcp-data     --project "$PROJECT" --region "$REGION" --format='value(status.url)')/mcp"
MCP_COMMS_URL="$(gcloud run services describe copilot-mcp-comms   --project "$PROJECT" --region "$REGION" --format='value(status.url)')/mcp"
MCP_CALENDAR_URL="$(gcloud run services describe copilot-mcp-calendar --project "$PROJECT" --region "$REGION" --format='value(status.url)')/mcp"

# Allow orchestrator SA to invoke the MCP services
for svc in copilot-mcp-data copilot-mcp-comms copilot-mcp-calendar; do
  gcloud run services add-iam-policy-binding "$svc" \
    --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$SA" --role "roles/run.invoker" \
    --quiet 2>&1 | grep -E "(bindings|etag)" | head -1
done

echo "==> deploying orchestrator at SHA $SHA"
gcloud run deploy copilot-orchestrator \
  --image "$REGISTRY/orchestrator:$SHA" \
  --project "$PROJECT" --region "$REGION" \
  --service-account "$SA" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi --cpu 1 \
  --max-instances 3 --concurrency 10 --timeout 300 \
  --set-env-vars "MCP_TRANSPORT=http,ORCHESTRATOR_MODEL=gemini-2.5-flash,SUBAGENT_MODEL=gemini-2.5-flash,SHADOW_MODE=true,MCP_DATA_URL=$MCP_DATA_URL,MCP_COMMS_URL=$MCP_COMMS_URL,MCP_CALENDAR_URL=$MCP_CALENDAR_URL,GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,SUPABASE_URL=$SUPABASE_URL_VAL" \
  --set-secrets "MCP_BEARER_TOKEN=copilot-mcp-bearer-token:latest,COPILOT_WEBHOOK_BEARER=copilot-webhook-bearer:latest,SUPABASE_SERVICE_ROLE_KEY=copilot-supabase-service-role-key:latest,COPILOT_DASHBOARD_TOKEN=copilot-dashboard-token:latest" \
  --quiet 2>&1 | tail -3

ORCH_URL=$(gcloud run services describe copilot-orchestrator --project "$PROJECT" --region "$REGION" --format='value(status.url)')

cat <<DONE
==================================================
ORCHESTRATOR URL : $ORCH_URL
MCP_DATA_URL     : $MCP_DATA_URL
MCP_COMMS_URL    : $MCP_COMMS_URL
MCP_CALENDAR_URL : $MCP_CALENDAR_URL
WEBHOOK BEARER   : (in /tmp/copilot/webhook-bearer)
==================================================

Smoke test:
  WB=\$(cat /tmp/copilot/webhook-bearer)
  curl -sS $ORCH_URL/healthz
  curl -sS -X POST $ORCH_URL/event \\
    -H "Authorization: Bearer \$WB" \\
    -H "Content-Type: application/json" \\
    -d '{"type":"booking.cancelled","business_id":"11111111-0000-0000-0000-000000000001","booking_id":"55555555-0000-0000-0000-000000000001"}'
DONE

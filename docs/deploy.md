# Deployment guide — Cloud Run

The system runs as 4 independently deployed Cloud Run services in the
`glossgo-platform` GCP project (`a01ee186bf9ebcbfc2e3e21e4c948737`).

| Service             | Image                              | Port | Public | Notes                          |
|---------------------|------------------------------------|------|--------|--------------------------------|
| `copilot-orchestrator` | `apps/orchestrator/Dockerfile`  | 8080 | yes    | POST `/event` entrypoint        |
| `copilot-mcp-data`     | `apps/mcp-data/Dockerfile`      | 8081 | no\*   | service-role Supabase read     |
| `copilot-mcp-comms`    | `apps/mcp-comms/Dockerfile`     | 8082 | no\*   | WhatsApp + approval queue      |
| `copilot-mcp-calendar` | `apps/mcp-calendar/Dockerfile`  | 8083 | no\*   | Booking writes (idempotent)    |

\* MCP servers are reachable only via `--ingress=internal-and-cloud-load-balancing`; the orchestrator authenticates with `MCP_BEARER_TOKEN`.

## Prerequisites (one-time)

```bash
# 1. Refresh user creds (only the human can do this — service accounts can't
#    enable services or create Cloud Run revisions in this project today)
gcloud auth login

gcloud config set project glossgo-platform
gcloud config set run/region europe-west4

# 2. Enable required APIs
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  pubsub.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# 3. One-time: Artifact Registry repo for our images
gcloud artifacts repositories create copilot \
  --repository-format=docker \
  --location=europe-west4 \
  --description="glossgo Salon Co-Pilot container images"

# 4. Push secrets to Secret Manager (sourced from Doppler)
for KEY in GEMINI_API_KEY SUPABASE_SERVICE_ROLE_KEY; do
  doppler secrets get "$KEY" --project glossgo --config prd --plain | \
    gcloud secrets create "copilot-${KEY,,}" --data-file=- --replication-policy=automatic \
    || doppler secrets get "$KEY" --project glossgo --config prd --plain | \
       gcloud secrets versions add "copilot-${KEY,,}" --data-file=-
done

# Random bearer for inter-service MCP auth
openssl rand -hex 32 | gcloud secrets create copilot-mcp-bearer-token \
  --data-file=- --replication-policy=automatic
```

## Build + deploy

```bash
REGION=europe-west4
REGISTRY="${REGION}-docker.pkg.dev/glossgo-platform/copilot"

# Build & push all 4 images
for svc in orchestrator mcp-data mcp-comms mcp-calendar; do
  gcloud builds submit "apps/$svc" \
    --tag "$REGISTRY/$svc:$(git rev-parse --short HEAD)" \
    --tag "$REGISTRY/$svc:latest"
done

# Deploy MCP servers (internal-only)
for svc in mcp-data mcp-comms mcp-calendar; do
  gcloud run deploy "copilot-$svc" \
    --image "$REGISTRY/$svc:latest" \
    --region "$REGION" \
    --no-allow-unauthenticated \
    --ingress internal-and-cloud-load-balancing \
    --set-env-vars "SUPABASE_URL=https://rpaaxlifkpgytiziyawq.supabase.co,MCP_TRANSPORT=http,SHADOW_MODE=true" \
    --set-secrets "SUPABASE_SERVICE_ROLE_KEY=copilot-supabase_service_role_key:latest,MCP_BEARER_TOKEN=copilot-mcp-bearer-token:latest" \
    --memory 512Mi --cpu 1 --max-instances 5 --concurrency 40
done

# Capture MCP URLs
MCP_DATA_URL=$(gcloud run services describe copilot-mcp-data    --region $REGION --format='value(status.url)')/mcp
MCP_COMMS_URL=$(gcloud run services describe copilot-mcp-comms  --region $REGION --format='value(status.url)')/mcp
MCP_CALENDAR_URL=$(gcloud run services describe copilot-mcp-calendar --region $REGION --format='value(status.url)')/mcp

# Deploy orchestrator (public)
gcloud run deploy copilot-orchestrator \
  --image "$REGISTRY/orchestrator:latest" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "MCP_TRANSPORT=http,ORCHESTRATOR_MODEL=gemini-2.5-flash,SUBAGENT_MODEL=gemini-2.5-flash,SHADOW_MODE=true,MCP_DATA_URL=$MCP_DATA_URL,MCP_COMMS_URL=$MCP_COMMS_URL,MCP_CALENDAR_URL=$MCP_CALENDAR_URL" \
  --set-secrets "GOOGLE_API_KEY=copilot-gemini_api_key:latest,MCP_BEARER_TOKEN=copilot-mcp-bearer-token:latest" \
  --memory 1Gi --cpu 1 --max-instances 5 --concurrency 20
```

## Smoke test

```bash
ORCH=$(gcloud run services describe copilot-orchestrator --region $REGION --format='value(status.url)')
curl -sS "$ORCH/healthz"
curl -sS -X POST "$ORCH/event" \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "booking.cancelled",
    "business_id": "11111111-0000-0000-0000-000000000001",
    "booking_id": "55555555-0000-0000-0000-000000000001"
  }'
```

## Switching to Vertex AI (post-billing setup)

When the user has billing on `glossgo-platform` enabled for Gemini 2.5 Pro,
flip the orchestrator to Vertex AI instead of AI Studio:

```bash
gcloud run services update copilot-orchestrator \
  --region $REGION \
  --update-env-vars "GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=glossgo-platform,GOOGLE_CLOUD_LOCATION=europe-west4,ORCHESTRATOR_MODEL=gemini-2.5-pro" \
  --remove-secrets "GOOGLE_API_KEY"
```

Cloud Run picks up the runtime service-account credentials automatically.

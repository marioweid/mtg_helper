# Operations Runbook

Copy-paste commands for the things you do more than once a year. For project conventions see `CLAUDE.md`.

## Compose layout

Two files. The base file is local-dev only; the prod file is a standalone Portainer stack.

| File | Purpose |
|---|---|
| `docker-compose.yml` | Local dev. Postgres + backend (`--reload`) + frontend (`pnpm dev`). Source dirs bind-mounted for hot reload. Data in a Docker-managed named volume. |
| `docker-compose.prod.yml` | Standalone production/Portainer stack. Uses host data under `${MTG_HELPER_DATA_DIR:-/srv/mtg-helper/data}`, production frontend build, and weekly `scryfall-sync`. |

The production file intentionally does **not** use Compose merge tags (`!reset`, `!override`) so it
works with current Portainer Git stacks. It publishes only the frontend to
`127.0.0.1:${FRONTEND_PORT:-3001}` by default; point the homeserver's existing reverse proxy /
Cloudflare Tunnel there. The `scryfall-sync` cron is prod-only; locally you trigger card sync from
the Admin page when you want fresh data.

## Portainer setup summary

1. Create persistent data directories on the homeserver:

```bash
sudo mkdir -p /srv/mtg-helper/data/postgres /srv/mtg-helper/data/qdrant
```

2. In Portainer, create a Git stack using:
   - Repository URL: this repo
   - Compose path: `docker-compose.prod.yml`
   - Branch: `main`
3. Add environment variables from `portainer.env.example` in the Portainer stack UI.
4. Enable automatic Git updates for the stack.
5. For immediate deploys on push, add the Portainer stack webhook URL as a repository `push` webhook.

## Local boot

```bash
# Required once: copy env template and fill in keys
cp backend/.env.example backend/.env
$EDITOR backend/.env   # set OPENAI_API_KEY; INTERNAL_API_TOKEN if you'll hit admin endpoints

# bring everything up (postgres, backend, frontend)
docker compose up -d --build

# tail logs
docker compose logs -f backend frontend

# stop
docker compose down
```

Ports: backend `:8000`, frontend `:3000`, postgres `:5432`.

> Local Compose loads `backend/.env` into the backend service and overrides `DATABASE_URL` with the
> `postgres` service hostname. The file is runtime-only and is not copied into images. No root
> `.env` is needed locally. `INTERNAL_API_TOKEN` only matters for `/api/v1/admin/*` endpoints.

## Prod boot with Portainer

1. On the homeserver, install Portainer Agent/CE and make sure the Docker host can build images.
2. Create the data directories once:

```bash
sudo mkdir -p /srv/mtg-helper/data/postgres /srv/mtg-helper/data/qdrant
```

3. In Portainer: **Stacks → Add stack → Git repository**.
   - Repository URL: this repo
   - Branch: `main`
   - Compose path: `docker-compose.prod.yml`
   - Environment variables: copy keys from `portainer.env.example` and fill secrets.
   - Leave `FRONTEND_BIND_ADDR=127.0.0.1` unless the tunnel/proxy runs on another host.
4. Deploy the stack.
5. Point the existing homeserver tunnel/proxy at `http://127.0.0.1:${FRONTEND_PORT}`.

Compose uses the stack environment only for interpolation and forwards each variable to the service
that needs it. In particular, `OPENAI_API_KEY` is available only to `backend`; PostgreSQL receives
only its database settings, `frontend` receives only URL/auth settings, and `scryfall-sync` receives
only `INTERNAL_API_TOKEN`.

CLI equivalent for testing on the server:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

## Assay tracing

The backend sends traces to your **existing** Assay instance; this stack does not deploy Assay.
Create a project and application in Assay, then save the project's ingest key. Set these in
Portainer's stack environment (production) or `backend/.env` (local Compose / `uv run`):

```dotenv
ASSAY_ENDPOINT=http://your-homeserver:8080
ASSAY_API_KEY=asy_your_project_ingest_key
ASSAY_APPLICATION=mtg-helper
```

- Use the application's **slug**, not its UUID, and a project ingest key, **not** the admin token.
  The application must belong to that key's project. Local-mode Assay still requires the key.
- The endpoint is Assay's HTTP(S) base URL (no UI path). It must be reachable **from the backend
  container**. `localhost` points to that container, not your homeserver. Use the server's LAN
  hostname/IP and published port, or its service name on an explicitly shared Docker network.
  Prefer HTTPS outside a trusted LAN; both the ingest key and AI content travel to this endpoint.
- Set all three values, or leave all three empty to disable tracing. Partial or malformed
  configuration fails startup rather than silently disabling the integration.
- Rebuild/redeploy the backend after this dependency change. Subsequent environment changes
  require recreating/redeploying the container, not just restarting it.
- Only the backend receives these variables. No frontend configuration is needed.

Traces include FastAPI requests, outbound HTTPX calls, and Pydantic AI agent/model/tool spans,
including **AI prompts, responses, and tool arguments/results**. Binary AI attachments are excluded.
Treat traces as private application data and configure retention/access controls in Assay.
HTTP bodies/headers are not explicitly captured; standard HTTP URL and error metadata can still
contain sensitive data. Database query spans remain disabled to avoid bulk-sync noise.

To verify, use an AI feature (for example the card coach), then open **Traces** in your Assay
application. Export runs in background batches, so allow a few seconds. Graceful backend shutdown
flushes pending spans. Collector outages/rejections do not fail API or AI requests; affected batches
are dropped and log `Assay trace export failed`. Check network reachability, project key, and slug
if traces are missing. `Assay tracing enabled` confirms configuration, not remote connectivity.

This is tracing integration only: it does not provision Assay projects or configure
evaluation/scoring datasets. The pinned `assay-sdk==0.4.0` supplies
Assay's JSON exporter; its private exporter bridge is isolated in `observability.py` because the
SDK has no public OpenTelemetry provider integration. OpenTelemetry versions match the SDK's pins.
There is no Logfire configuration or fallback (Pydantic AI retains its own transitive `logfire-api`
shim, which does not export to Logfire).

### Assistant sessions

Open **Sessions** in your Assay application to follow a chat across multiple assistant turns.
No additional environment variables or database migrations are needed. Rebuild/redeploy both
backend and frontend for the request wiring.

- The assistant chat page generates a random conversation UUID per open chat and reuses it for
  follow-ups. Reloading/reopening the page or switching decks starts a new chat/session, matching
  the lifetime of the visible in-memory history. Retries in the same chat retain its session ID.
- The backend derives an opaque Assay session ID scoped to the authenticated account, deck, and
  conversation UUID. Reusing a client UUID for another account or deck cannot merge sessions.
  This identifier is correlation metadata, never authentication or permission to read a transcript.
- Each turn gets one independent `assistant.turn` root trace with the current question and visible
  reply. Model/tool child spans retain detailed evidence and provider history. Memory-only commands
  are included too. Background turns remain open until completion; failed turns record their error.
- HTTP start requests and SSE connections remain ordinary traces, not duplicate session turns.
  Each assistant turn links back to its initiating HTTP request.
- API callers can send `conversation_id` (a UUID) in both `POST /api/v1/decks/{deck_id}/coach` and
  `POST /api/v1/decks/{deck_id}/coach/start`. Reuse it for follow-ups and generate a new UUID when
  clearing chat history. Omit it for a standalone one-turn session; invalid UUIDs return 422.

Session grouping uses Assay's documented OpenTelemetry `session.id` root attribute and
`gen_ai.conversation.id` on GenAI spans, on the same provider as the rest of our tracing.
It does not load conversation history from Assay: the assistant still receives its bounded history
from the chat page, and deck memory remains in the application's database. Existing traces are not
retroactively grouped. Without Assay configuration, chat behavior is unchanged and nothing exports.

## Database

Schema is `backend/src/mtg_helper/sql/schema.sql` — idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE`). Auto-applied on backend startup via `apply_schema()` and on first compose up via `docker-entrypoint-initdb.d`. There is no separate migration tool — edit `schema.sql`, restart the backend.

```bash
# re-apply schema after editing schema.sql (local)
docker compose restart backend

# psql shell
docker compose exec postgres psql -U mtg -d mtg_helper

# wipe local DB (DESTRUCTIVE — drops the volume)
docker compose down -v && docker compose up -d
```

### Production schema apply

Schema runs on container start. For a one-off forced re-apply in Portainer, restart the `backend` service. CLI fallback:

```bash
cd /opt/mtg-helper
docker compose -f docker-compose.prod.yml --env-file .env.prod restart backend
```

## Card data sync

Easiest: sign in as an admin user, click **Admin** in the nav (only visible to addresses listed in `ADMIN_EMAILS`), use the buttons. The page calls the same endpoints below.

Required env (frontend, in `.env.local` for dev / Portainer stack env for prod):

```
ADMIN_EMAILS="you@example.com,other@example.com"
```

Backend's `ADMIN_EMAILS` (in `backend/.env` / Portainer stack env) must contain the same set — frontend just hides the button, backend enforces.

Three admin endpoints, in order, do a full refresh: pull Scryfall → tag → embed into Qdrant.

```bash
TOKEN="<INTERNAL_API_TOKEN from .env>"
BASE="http://localhost:8000"   # local; use https://<your-host> for prod

curl -X POST -H "X-Internal-Token: $TOKEN" "$BASE/api/v1/admin/sync-cards"
curl -X POST -H "X-Internal-Token: $TOKEN" "$BASE/api/v1/admin/tag-cards"
curl -X POST -H "X-Internal-Token: $TOKEN" "$BASE/api/v1/admin/embed-cards"
```

Weekly auto-sync runs **only in prod** via the `scryfall-sync` service defined in `docker-compose.prod.yml`. Locally, trigger it manually from the Admin page (or with the curl commands above) when you want fresh card data. Initial sync also runs on backend startup if `cards` table is empty.

## Deploy pipeline

Use Portainer GitOps so the homeserver redeploys itself from this repo.

Recommended setup:

1. In the Portainer Git stack, enable **Automatic updates**.
2. Choose either polling or webhook updates. For immediate deploys on push, copy the Portainer stack webhook URL.
3. In GitHub/Gitea/etc., add a repository webhook:
   - Event: `push`
   - Branch: `main`
   - URL: the Portainer webhook URL
   - Content type: `application/json`
4. On each push to `main`, Portainer pulls the repo and runs the production compose stack again.

If your Portainer install offers a “force rebuild/redeploy” option for Git updates, enable it so local images are rebuilt from the new commit.

## VM lifecycle

VM is a GCP spot instance. It can get preempted (= STOPPED). A Cloud Scheduler job (`mtg-helper-auto-restart`) starts it on a schedule.

```bash
# status
gcloud compute instances describe mtg-helper \
  --zone=europe-west1-b --format='value(status)'

# manual start (after preemption)
gcloud compute instances start mtg-helper --zone=europe-west1-b

# manual stop
gcloud compute instances stop mtg-helper --zone=europe-west1-b

# SSH (interactive)
gcloud compute ssh mtg-helper --zone=europe-west1-b --tunnel-through-iap

# trigger the auto-restart job once
gcloud scheduler jobs run mtg-helper-auto-restart --location=europe-west1
```

## Production stack CLI fallback

Prefer Portainer for normal deploys. If you need to manage the stack by SSH:

```bash
cd /opt/mtg-helper
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$COMPOSE ps
$COMPOSE logs -f backend
$COMPOSE restart backend
$COMPOSE up -d --build --force-recreate backend frontend
$COMPOSE down            # stops everything; data persists under MTG_HELPER_DATA_DIR
```

## Snapshots & restore

Daily disk snapshots managed by Terraform (`google_compute_resource_policy`).

```bash
# list snapshots for the data disk
gcloud compute snapshots list --filter='sourceDisk~mtg-helper-data' \
  --sort-by='~creationTimestamp'

# restore: detach data disk, create a new disk from snapshot, attach it
# (manual — do this only for disaster recovery)
```

## Infrastructure (Terraform)

```bash
cd infra/terraform

terraform plan
terraform apply

# specific target (e.g. just IAM)
terraform apply -target=google_project_iam_member.deployer_os_login
```

Required vars in `infra/terraform/terraform.tfvars` (gitignored). See `terraform.tfvars.example`.

## Common deploy failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Permission denied (publickey)` for `sa_<digits>` | `google-guest-agent` disabled on VM (regression after image refresh / spot recreate) | SSH in, `sudo systemctl enable --now google-guest-agent`. Startup script also handles this on next boot. |
| `iam.serviceAccounts.actAs` denied | Deployer SA missing `roles/iam.serviceAccountUser` on the VM SA | `terraform apply` (binding lives in `deployer.tf`) |
| `No such file or directory: ~/mtg-helper` | Deployer SA's home is `/home/sa_<numeric>/`, not personal user's | Always use absolute `/opt/mtg-helper` + `sudo` in workflow |
| Backend container restart-loops after deploy | Schema apply error or missing env var | `$COMPOSE logs --tail=100 backend` on the VM |
| Sync endpoint returns 401 with `X-Internal-Token` | Backend `.env` missing `INTERNAL_API_TOKEN`, or value mismatched between caller and server | Compare `cat .env` on VM/local with `$INTERNAL_API_TOKEN` env in cron container |

## Quick checks (CI commands)

```bash
# backend
cd backend
uv run ruff check . && uv run ruff format --check .
uv run ty check src/
uv run pytest -q

# frontend (needs node 22)
cd frontend
PATH="/usr/local/Cellar/node@22/22.22.2_1/bin:$PATH" pnpm exec tsc --noEmit
PATH="/usr/local/Cellar/node@22/22.22.2_1/bin:$PATH" pnpm build
```

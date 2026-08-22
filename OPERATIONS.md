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

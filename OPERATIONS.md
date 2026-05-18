# Operations Runbook

Copy-paste commands for the things you do more than once a year. For project conventions see `CLAUDE.md`.

## Compose layout

Two files. The base one is the local-dev stack; the prod overlay layers on top.

| File | Purpose |
|---|---|
| `docker-compose.yml` | Local dev. Postgres + Qdrant + backend (`--reload`) + frontend (`pnpm dev`). Source dirs bind-mounted for hot reload. Data in Docker-managed named volumes. |
| `docker-compose.prod.yml` | Additive overlay for the GCP VM. Binds `pgdata` / `qdrantdata` to `/srv/mtg-helper/data/*`, strips host ports, swaps to `.env.prod`, adds `cloudflared` and the weekly `scryfall-sync` cron. Never run standalone. |

The `scryfall-sync` cron and Cloudflare Tunnel are prod-only; locally you trigger card sync from the Admin page when you want fresh data.

## Local boot

```bash
# Required once: copy env template and fill in keys
cp backend/.env.example backend/.env
$EDITOR backend/.env   # set GEMINI_API_KEY; INTERNAL_API_TOKEN if you'll hit admin endpoints

# bring everything up (postgres, qdrant, backend, frontend)
docker compose up -d --build

# tail logs
docker compose logs -f backend frontend

# stop
docker compose down
```

Ports: backend `:8000`, frontend `:3000`, postgres `:5432`, qdrant `:6333`.

> No root `.env` is needed locally — `INTERNAL_API_TOKEN` only matters if you call `/api/v1/admin/*` endpoints, and the backend reads it from `backend/.env`.

## Prod boot (on the VM)

```bash
gcloud compute ssh mtg-helper --zone=europe-west1-b --tunnel-through-iap

# from inside the VM
cd /opt/mtg-helper
sudo docker compose \
  -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod \
  up -d --build
```

`.env.prod` lives at `/opt/mtg-helper/.env.prod` and supplies both the env vars consumed inside containers (Gemini key, NextAuth secrets, etc.) and the values interpolated into the compose file itself (`INTERNAL_API_TOKEN` for the sync cron, `CF_TUNNEL_TOKEN` for cloudflared).

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

Schema runs on container start. For a one-off forced re-apply on the VM:

```bash
gcloud compute ssh mtg-helper --zone=europe-west1-b --tunnel-through-iap --command="
  sudo docker compose -f /opt/mtg-helper/docker-compose.yml \
    -f /opt/mtg-helper/docker-compose.prod.yml \
    --env-file /opt/mtg-helper/.env.prod restart backend
"
```

## Card data sync

Easiest: sign in as an admin user, click **Admin** in the nav (only visible to addresses listed in `ADMIN_EMAILS`), use the buttons. The page calls the same endpoints below.

Required env (frontend, in `.env.local` for dev / `.env.prod` for VM):

```
ADMIN_EMAILS="you@example.com,other@example.com"
```

Backend's `admin_emails` (in `backend/.env` / `.env.prod`) must contain the same set — frontend just hides the button, backend enforces.

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

Push to `main` triggers `.github/workflows/deploy.yml`. Path filter: `backend/**`, `frontend/**`, compose files, the workflow itself.

```bash
# trigger manually (no source change)
gh workflow run deploy.yml

# watch the run
gh run watch

# inspect last run
gh run view --log
```

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

## Production stack on the VM

```bash
gcloud compute ssh mtg-helper --zone=europe-west1-b --tunnel-through-iap

# from inside the VM
cd /opt/mtg-helper
COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod"

$COMPOSE ps
$COMPOSE logs -f backend
$COMPOSE restart backend
$COMPOSE up -d --force-recreate backend frontend
$COMPOSE down            # stops everything (data persists on /srv/mtg-helper/data)
```

`/opt/mtg-helper` is a symlink to `/srv/mtg-helper/data/repo` so the repo survives VM replacement. `.env.prod` lives in that dir.

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

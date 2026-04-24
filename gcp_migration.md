# Dual-target deploy: local + GCP (single VM)

## Context

This doc is **not** a one-way migration away from local. Goal: the GCP target is the same `docker-compose` stack you run on your laptop, just on one Compute Engine VM in `europe-west1`. No Cloud Run, no Cloud SQL, no Qdrant Cloud, no pgvector refactor — the stack is identical to what `docker compose up` gives you today.

- **Local dev loop is unchanged.** `docker compose up` → full stack with hot reload.
- **GCP target = same compose stack on one VM.** SSH in via IAP, `docker compose up -d`; a `cloudflared` sidecar opens an outbound tunnel to Cloudflare, which routes `<hostname>` to `frontend:3000` and gates access via Cloudflare Access (Google SSO / email OTP). No public ports on the VM. Mental model: *the VM is your laptop in Belgium.*
- **Local Terraform.** `terraform apply` from the laptop provisions the VM + disk + firewall. CI automation (GHA + WIF) is deferred until this manual path is stable.

User is in Germany → `europe-west1` (Belgium, cheapest EU region).

### Existing surface (verified)

- Backend FastAPI (Python 3.13), env vars: `DATABASE_URL`, `GEMINI_API_KEY`, `SCRYFALL_BULK_DATA_URL`.
- Frontend Next.js 15 App Router.
- Postgres 16, schema in `backend/src/mtg_helper/sql/schema.sql`.
- Qdrant `mtg_cards` collection, ~22k × 1536d vectors, used by `retrieval_service.py`, `embedding_service.py`, `ai_service.py`, `tag_service.py`.
- Weekly Scryfall bulk sync via `scryfall-sync` alpine cron container.
- Auth: none. `account_id` UUID in localStorage; admin routes unauthenticated.

## Architecture — local vs GCP

| Component | Local (docker-compose) | GCP (one VM, docker-compose) |
|---|---|---|
| Backend | compose service `backend`, port 8000 | **same container**, reached through the Cloudflare tunnel → `frontend` → `/api/*` rewrite |
| Frontend | compose service `frontend`, port 3000 | **same container**, reached through the Cloudflare tunnel |
| Postgres | `postgres:16`, `pgdata` named volume | `postgres:16`, `pgdata` on an attached persistent disk |
| Qdrant | `qdrant/qdrant:v1.17`, `qdrantdata` named volume | `qdrant/qdrant:v1.17`, `qdrantdata` on the same persistent disk |
| Weekly sync | `scryfall-sync` curl loop | same container, unchanged |
| Public ingress | — | **Cloudflare Tunnel** (`cloudflared` container, outbound-only QUIC to the Cloudflare edge). TLS terminates at Cloudflare. **Cloudflare Access** gates the hostname with Google SSO / email OTP before the app sees a request. |
| Secrets | `.env` (gitignored) | `.env.prod` on the VM (600 perms), `scp`'d once |
| Images | built locally | built on the VM from the cloned repo |

The VM has **no public ingress ports open**. Only SSH reaches it, via IAP. All user traffic arrives through the tunnel.

Expected cost:

- **e2-medium** (2 vCPU burstable, 4 GB RAM, `europe-west1`) ≈ **€23–26/mo** — recommended, comfortable headroom.
- **e2-small** (2 vCPU burstable, 2 GB RAM) ≈ **€11–14/mo** — works but tight; will swap under load.
- Persistent disk (50 GB balanced) + static external IP + egress add **< €2/mo** at this traffic.

### Why a single VM and not Cloud Run

Scale-to-zero does not help here: Qdrant and Postgres are always-on. Splitting the stack across Cloud Run + Cloud SQL + a separate Qdrant host adds three moving parts, two IAM boundaries, and Secret Manager wiring — all to serve a handful of users. One VM with the existing `docker-compose.yml` is the lowest-complexity GCP target that preserves the contract already working on the laptop.

### VM sizing

Steady-state RAM with 22k cards loaded:

- Qdrant HNSW: ~200–300 MB resident.
- Postgres idle: ~100 MB.
- FastAPI + uvicorn: ~150 MB.
- Next.js: ~250 MB (dev mode is heavier than standalone prod — budget accordingly).
- OS + Docker daemon: ~200 MB.

Total ≈ 1.2–1.6 GB. **e2-medium (4 GB)** leaves ~2.4 GB for spikes, the sync job, and OS cache — recommended. **e2-small (2 GB)** technically boots but will swap during Scryfall sync or large Gemini embeddings; only use it if the ~€12/mo savings matter.

## Auth — include in this deploy (do NOT postpone)

Cloudflare Access in front of the tunnel is the network gate — it decides who can reach the site at all. In-app Google OAuth is still required as the **application-level identity**: it populates `google_sub`, drives `admin_emails`, and binds per-user data. Migrating localStorage `account_id` → `google_sub` **after** go-live is a second data migration — avoid that by shipping auth together. Treat Access as a fence, in-app OAuth as the user record.

Approach:

- Frontend: **Auth.js v5** (NextAuth) with Google provider, JWT session. Forward `id_token` to the backend via a Next route handler that injects `Authorization: Bearer …` server-side (token never leaves the server).
- Backend: FastAPI dependency `get_current_account` using `google.oauth2.id_token.verify_oauth2_token` (already a transitive dep of `google-genai`). Validates `aud`, `iss`, `exp`. JWKS cached by the library.
- Schema: `ALTER TABLE accounts ADD google_sub TEXT UNIQUE, ADD email TEXT`. First login upserts by `google_sub`.
- Admin gate: `email IN ADMIN_EMAILS` env list.

## Public access: Cloudflare Tunnel + Access

No ports are opened on the VM. A `cloudflared` container inside compose opens an outbound QUIC tunnel to the Cloudflare edge; user traffic enters from Cloudflare and exits to the internal compose network — one direction only.

- **Domain.** The domain must use Cloudflare nameservers (free plan is enough). Add it to Cloudflare, switch nameservers at the registrar.
- **Tunnel.** Create it once via the Zero Trust dashboard (Networks → Tunnels → Create) or `cloudflared tunnel create mtg-helper`. Copy the docker run token into `.env.prod` as `CF_TUNNEL_TOKEN`. `cloudflared tunnel route dns <tunnel-name> <hostname>` (or the dashboard) creates the CNAME.
- **Public Hostname.** In the tunnel config: `<hostname>` → `http://frontend:3000`. The existing Next.js `/api/*` rewrite forwards API calls to `backend:8000`, so a single public hostname pointed at the frontend is sufficient. If the rewrite is ever removed, add a second public hostname → `http://backend:8000`.
- **Cloudflare Access.** Add an Access application covering `<hostname>` with policy `Emails include mario.weidner@gmx.de` (plus any invitees). Identity providers: Google SSO and/or email one-time PIN. Access issues a signed JWT cookie; unauthenticated requests are redirected to Cloudflare's login page — nothing installed on the client, works on mobile browsers.
- **TLS.** Cloudflare issues and renews the edge certificate automatically — no Let's Encrypt, no Caddy, no `APP_DOMAIN` binding.
- **OAuth redirect URI.** `https://<cf-hostname>/api/auth/callback/google` (real FQDN, satisfies Google's "no raw IP" rule).

Two identity layers, intentional: Cloudflare Access gates the network; in-app Google OAuth binds user rows. Keep both.

## Compose changes

Keep `docker-compose.yml` exactly as it is — that's the local dev contract.

Add **`docker-compose.prod.yml`** as an override applied on the VM:

- Adds a `cloudflared` service — outbound tunnel only, no `ports:` stanza:
  ```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${CF_TUNNEL_TOKEN}
    depends_on: [frontend, backend]
  ```
- Removes the dev bind-mounts (`./backend/src:/app/src`, frontend volume mounts) so the VM runs the baked image.
- Sets `restart: unless-stopped` on all services.
- Rebinds `pgdata` and `qdrantdata` to paths under `/srv/mtg-helper/data/` (the persistent disk mount) so snapshots work at the disk level.
- Removes the `ports:` stanzas on `backend` and `frontend` — they are reachable only through the internal compose network, which is what the tunnel connects to by service name.

Deploy command on the VM:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Dev Dockerfiles are reused on the VM — no prod multi-stage images, no Next `output: "standalone"` changes. This is the "as close to local as possible" choice; revisit only if image build/pull time on the VM becomes annoying.

## Files to Create

```
infra/terraform/
  versions.tf  providers.tf  variables.tf  terraform.tfvars.example
  apis.tf           # enable compute.googleapis.com
  compute.tf        # google_compute_instance + attached data disk (no static external IP)
  firewall.tf       # SSH via IAP only (35.235.240.0/20) — no 80/443 rule
  snapshots.tf      # daily resource_policy on the data disk (7-day retention)
  outputs.tf        # vm_name (+ ephemeral external IP if one is present)
backend/src/mtg_helper/auth.py
backend/src/mtg_helper/sql/migrations/002_google_sub.sql
frontend/app/api/auth/[...nextauth]/route.ts
frontend/lib/auth.ts
frontend/middleware.ts
docker-compose.prod.yml
.env.example                 # repo root
deploy.sh                    # ssh + git pull + docker compose up -d --build
```

No `cloud_run_*.tf`, no `cloud_sql.tf`, no `artifact_registry.tf`, no `secrets.tf`, no `scheduler.tf`, no `003_pgvector.sql`, no `Caddyfile`, no static-IP resource — none are part of the single-VM + tunnel model.

The Cloudflare tunnel is created once in the Zero Trust dashboard (or via the `cloudflared` CLI) and the resulting token lives in `.env.prod` as `CF_TUNNEL_TOKEN`. Not a Terraform resource in this pass — the Cloudflare Terraform provider is optional polish later.

## Files to Modify

- `backend/src/mtg_helper/routers/*.py` — replace `X-Account-Id` header / path-param `account_id` with `Depends(get_current_account)`.
- `backend/src/mtg_helper/routers/admin.py` — add admin email gate.
- `backend/src/mtg_helper/config.py` — add `google_oauth_client_id`, `admin_emails`. Qdrant config stays.
- `frontend/lib/account.ts` — replace with `useSession()` / `auth()` from Auth.js.
- `frontend/lib/api.ts:212-217` — drop `X-Account-Id`; route through a Next handler that injects the bearer token server-side.
- `frontend/next.config.ts` — confirm the existing `/api/*` → backend rewrite stays (the tunnel points at the frontend only). No code change expected.
- `docker-compose.yml` — no structural change; the prod override is purely additive.

Optional hardening (defer): `backend/src/mtg_helper/auth.py` can additionally verify the `Cf-Access-Jwt-Assertion` header as a second gate. Not required — Cloudflare Access is already the network fence and the in-app Google OAuth is the user-identity layer.

Nothing in `retrieval_service.py`, `embedding_service.py`, `ai_service.py`, `tag_service.py`, `main.py`, `db.py`, or the Dockerfiles needs to change for this deploy — Qdrant stays, schema stays.

## `.env.example` (commit at repo root)

```bash
# === GCP (Terraform) ===
GCP_PROJECT_ID=             # console.cloud.google.com → project picker
GCP_REGION=europe-west1
GCP_ZONE=europe-west1-b
VM_MACHINE_TYPE=e2-medium   # e2-small works but is tight; e2-medium recommended
VM_NAME=mtg-helper

# === App (same vars as today, now also used on the VM) ===
DATABASE_URL=postgresql://mtg:mtg_prod@postgres:5432/mtg_helper
GEMINI_API_KEY=             # aistudio.google.com → Get API Key
SCRYFALL_BULK_DATA_URL=https://api.scryfall.com/bulk-data

# === Google Sign-In (OAuth 2.0 Web client) ===
# console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID → Web application
# Authorized redirect URI: https://<cf-hostname>/api/auth/callback/google
# OAuth consent screen: External, Testing, add yourself as test user
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
NEXTAUTH_SECRET=            # `openssl rand -base64 32`
NEXTAUTH_URL=               # https://<cf-hostname>
ADMIN_EMAILS=mario.weidner@gmx.de

# === Cloudflare Tunnel + Access ===
# Zero Trust dashboard → Networks → Tunnels → Create a tunnel → copy the docker run token.
# Access application + policy are configured in the dashboard, not via env vars.
CF_TUNNEL_TOKEN=
```

The Postgres password lives inside `DATABASE_URL` on the VM's `.env.prod`. Rotate by editing the file and `docker compose restart postgres backend`. `.env` is for local compose only; `.env.prod` ships to the VM via `gcloud compute scp` once.

## Deploy Phases (each ends in a working state)

1. **Baseline locally** — confirm `docker compose up` gives a working stack on the laptop. No work here unless something regressed.
2. **Auth** — Auth.js on frontend, FastAPI dependency, `002_google_sub.sql` migration. Tested against `http://localhost:3000` before touching the cloud. (Optional sequencing: ship to the VM first behind Cloudflare Access only — which already blocks unauthenticated users at the edge — and add in-app Google Sign-In after. Do this only if the in-app auth plumbing isn't ready; Access alone is safe but you still need in-app auth for `google_sub` and `admin_emails` before inviting more users.)
3. **Prod compose + cloudflared** — add `docker-compose.prod.yml` with the `cloudflared` service. Dry-run locally: create a throwaway tunnel in the Cloudflare dashboard, drop its token into `.env.prod`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d`, and browse via the Cloudflare hostname before any GCP resources exist.
4. **Terraform: VM + disk + firewall** — `terraform apply` creates the e2-medium instance in `europe-west1-b`, a 50 GB balanced persistent disk mounted at `/srv/mtg-helper/data/`, and a firewall rule allowing SSH **only via IAP** (`35.235.240.0/20`). No `tcp:80,443` rule, no static external IP — the tunnel is outbound-only.
5. **First deploy** — `gcloud compute scp .env.prod mtg-helper:~/mtg-helper/.env.prod`, `gcloud compute ssh mtg-helper` (IAP), install Docker + compose plugin (or bake via cloud-init), `git clone <repo>`, `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
6. **Cloudflare Tunnel + Access + Google OAuth** —
   1. Add the domain to Cloudflare (free plan), switch nameservers at the registrar.
   2. Create the production tunnel (`cloudflared tunnel create mtg-helper` or dashboard), copy its token into `.env.prod`, `docker compose restart cloudflared`.
   3. In Zero Trust → the tunnel's **Public Hostnames**: `<hostname>` → `http://frontend:3000`.
   4. In Zero Trust → **Access → Applications**: add an application covering `<hostname>` with policy `Emails include <admins/invitees>`, identity providers Google SSO and/or Email OTP.
   5. Update the Google OAuth client's authorized redirect URI to `https://<cf-hostname>/api/auth/callback/google` and set `NEXTAUTH_URL=https://<cf-hostname>`; `docker compose restart frontend`.
7. **Snapshot schedule** — Terraform `google_compute_resource_policy` with a daily snapshot window + 7-day retention, attached to the data disk.
8. *(Deferred)* **GitHub Actions** — auto `ssh + git pull + docker compose up -d --build` on push to `main`, via a dedicated `deployer` service account key (or WIF when you're ready).

## Verification

- `gcloud compute instances describe $VM_NAME --zone=$GCP_ZONE --format='value(status)'` → `RUNNING`.
- On the VM: `docker compose ps` — every service `Up`; Postgres `(healthy)`; `cloudflared` logs show `Registered tunnel connection`.
- `curl -sI https://<cf-hostname>` without an Access cookie → 302 to the Cloudflare login page (not 200).
- Browser session after Access login → 200; Google Sign-In inside the app completes; session cookie present; no `mtg_helper_account_id` in localStorage.
- `gcloud compute firewall-rules list` — no rule permits `tcp:80` or `tcp:443` from `0.0.0.0/0`; only the IAP SSH rule exists.
- If the VM has an ephemeral external IP at all: `nc -zv <ip> 443` from outside times out.
- Qdrant live (on the VM): `docker compose exec qdrant curl -sf http://localhost:6333/collections/mtg_cards` → ~22k points.
- Postgres live (on the VM): `docker compose exec postgres psql -U mtg -d mtg_helper -c "SELECT count(*) FROM cards;"` → ~22k.
- Weekly sync: `docker compose logs scryfall-sync` shows the loop. Force-run: `docker compose exec backend curl -X POST http://localhost:8000/api/v1/admin/sync-cards` (with an admin bearer token).
- Unauthenticated `POST /api/v1/admin/sync-cards` from the internet → blocked by Access before reaching the app; a non-admin email that passes Access still → 403 from the backend gate.
- Cloudflare Access audit log shows the login events.
- Snapshots: 24 h after apply, `gcloud compute snapshots list` shows at least one entry.
- Cost: GCP Billing report, project filter, daily ≈ **€0.75–0.85** (e2-medium) or **€0.35** (e2-small). Cloudflare Tunnel + Access (for ≤50 users) is free.

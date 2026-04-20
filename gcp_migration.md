Migration: mtg_helper → GCP

 Context

 App today runs only via docker-compose on user's laptop. Goal: deploy to GCP with Terraform, scale-to-zero pricing for a handful of users, no Kubernetes. Local compose dev workflow stays intact. Replace
  localStorage account_id bootstrap with Google Sign-In so admin endpoints (currently unauthenticated) can be safely exposed on a public Cloud Run URL. User is in Germany → deploy to europe-west1
 (Belgium, cheapest eu region).

 Existing surface (verified):
 - Backend FastAPI (Python 3.13), 3 env vars: DATABASE_URL, GEMINI_API_KEY, SCRYFALL_BULK_DATA_URL
 - Frontend Next.js 15 App Router, dev-only Dockerfile (no pnpm build stage, no standalone output)
 - Postgres 16 (~8 tables, GIN/trgm/fts indexes — backend/src/mtg_helper/sql/schema.sql)
 - Qdrant collection mtg_cards, ~22k × 1536d vectors, used by retrieval_service.py, embedding_service.py, ai_service.py, tag_service.py
 - Weekly Scryfall bulk sync via alpine cron container
 - Auth: none. account_id UUID in localStorage; admin routes unauthenticated.

 Recommended Stack & Cost (~€10–15/mo)

 ┌──────────────┬───────────────────────────────────────────────┬────────────────────────────────────────────────┐
 │  Component   │                  GCP service                  │                     Notes                      │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Backend      │ Cloud Run (1 vCPU/512 MiB, min=0, max=2)      │ scales to zero                                 │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Frontend     │ Cloud Run with Next.js output: "standalone"   │ one stack, one IAM boundary, no Vercel lock-in │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Postgres     │ Cloud SQL db-f1-micro, 10 GB HDD, single zone │ ~€8–10 — biggest cost                          │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Vector store │ pgvector inside Cloud SQL (replaces Qdrant)   │ see decision below                             │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Weekly sync  │ Cloud Run Job + Cloud Scheduler               │ <€0.10                                         │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Secrets      │ Secret Manager                                │ mounted as env into Cloud Run                  │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ Images       │ Artifact Registry (one repo mtg-helper)       │ ~€0.50                                         │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ CI           │ GitHub Actions + Workload Identity Federation │ no SA JSON keys                                │
 ├──────────────┼───────────────────────────────────────────────┼────────────────────────────────────────────────┤
 │ TLS          │ Cloud Run managed cert + domain mapping       │ free                                           │
 └──────────────┴───────────────────────────────────────────────┴────────────────────────────────────────────────┘

 Qdrant → pgvector (recommended)

 22k × 1536d ≈ 135 MB; HNSW index trivial for db-f1-micro. Eliminates a service, one fewer connection pool, transactional consistency, fewer secrets, no extra Terraform resources, no babysitting a VM.
 Self-hosting Qdrant on an e2-micro (~€5/mo, no scale-to-zero) or Qdrant Cloud free tier are valid alternatives but each adds an external dependency to maintain. Refactor touches 4 service files + a SQL
 migration adding embedding vector(1536) column to cards.

 Auth — include in this migration (do NOT postpone)

 Honest assessment: Cloud Run URLs are public; admin endpoints (/admin/sync-cards, /admin/embed-cards) cannot ship without auth. Migrating localStorage account_id → google_sub after go-live means a
 second data migration. Auth.js + a 30-line FastAPI dependency is roughly 1 day of work — small relative to the Terraform/pgvector work. Ship together.

 Approach:
 - Frontend: Auth.js v5 (NextAuth) with Google provider, JWT session. Forward id_token to backend via a Next route handler proxy that injects Authorization: Bearer … server-side (token never leaves the
 server).
 - Backend: FastAPI dependency get_current_account using google.oauth2.id_token.verify_oauth2_token (already a transitive dep of google-genai). Validates aud, iss, exp. JWKS cached by the library.
 - Schema: ALTER TABLE accounts ADD google_sub TEXT UNIQUE, ADD email TEXT. First login upserts by google_sub.
 - Admin gate: email IN ADMIN_EMAILS env list.

 Files to Create

 infra/terraform/
   versions.tf  providers.tf  backend.tf  variables.tf  terraform.tfvars.example
   apis.tf  artifact_registry.tf  secrets.tf  cloud_sql.tf
   cloud_run_backend.tf  cloud_run_frontend.tf  cloud_run_job_sync.tf
   scheduler.tf  iam.tf  domain.tf  outputs.tf
 infra/terraform/bootstrap/   # state bucket + WIF pool, run once with local state
 .env.example                 # repo root, see below
 .github/workflows/deploy.yml # build + push + deploy on push to main, via WIF
 backend/src/mtg_helper/auth.py
 backend/src/mtg_helper/sql/migrations/002_google_sub.sql
 backend/src/mtg_helper/sql/migrations/003_pgvector.sql
 frontend/app/api/auth/[...nextauth]/route.ts
 frontend/lib/auth.ts
 frontend/middleware.ts

 Flat Terraform layout (no modules) — only ~10 resources, modules would be over-engineering.

 Files to Modify

 - backend/Dockerfile — add prod stage: multi-stage uv sync --no-dev --frozen, python:3.13-slim, USER 1000:1000, CMD uvicorn mtg_helper.main:app --host 0.0.0.0 --port ${PORT:-8080}. Keep dev stage.
 - frontend/Dockerfile — add builder (pnpm build) + runner (copy .next/standalone, .next/static, public, CMD ["node","server.js"], ENV PORT=8080). Keep dev stage.
 - frontend/next.config.ts — output: "standalone".
 - docker-compose.yml — postgres image → pgvector/pgvector:pg16; move qdrant under profiles: ["legacy"]; add target: dev to backend/frontend builds.
 - backend/src/mtg_helper/config.py — add google_oauth_client_id, admin_emails; drop qdrant_url.
 - backend/src/mtg_helper/main.py:43 — drop AsyncQdrantClient init.
 - backend/src/mtg_helper/services/{retrieval,embedding,ai,tag}_service.py — pgvector via asyncpg (use pgvector.asyncpg.register_vector on pool init).
 - backend/src/mtg_helper/routers/*.py — replace X-Account-Id header / path-param account_id with Depends(get_current_account).
 - backend/src/mtg_helper/routers/admin.py — add admin email gate.
 - frontend/lib/account.ts — replace with useSession()/auth() from Auth.js.
 - frontend/lib/api.ts:212-217 — drop X-Account-Id; route through Next handler that injects bearer token server-side.

 .env.example (commit at repo root)

 # === GCP project (Terraform + gcloud) ===
 GCP_PROJECT_ID=             # console.cloud.google.com → project picker
 GCP_REGION=europe-west1     # Belgium; closest cheap eu region
 GCP_ARTIFACT_REPO=mtg-helper

 # === Cloud SQL ===
 DATABASE_URL=               # postgresql://mtg:<pw>@/mtg_helper?host=/cloudsql/<conn-name>
 CLOUDSQL_CONNECTION_NAME=   # GCP console → SQL → instance overview, format <project>:<region>:<instance>

 # === Gemini ===
 GEMINI_API_KEY=             # aistudio.google.com → Get API Key

 # === Google Sign-In (OAuth 2.0 Web client) ===
 # console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID → Web application
 # Authorized redirect URI: https://<frontend-url>/api/auth/callback/google
 # Plus OAuth consent screen: External, Testing, add yourself as test user
 GOOGLE_OAUTH_CLIENT_ID=
 GOOGLE_OAUTH_CLIENT_SECRET=
 NEXTAUTH_SECRET=            # `openssl rand -base64 32`
 NEXTAUTH_URL=               # https://app.<your-domain> (prod) | http://localhost:3000 (dev)
 ADMIN_EMAILS=mario.weidner@gmx.de

 # === Scryfall ===
 SCRYFALL_BULK_DATA_URL=https://api.scryfall.com/bulk-data

 # === Frontend → backend (server-side only) ===
 BACKEND_ORIGIN=             # https://<backend-cloud-run-url> (prod) | http://backend:8000 (compose)

 # === GitHub repo secrets (NOT in .env) ===
 # GCP_WIF_PROVIDER=projects/<num>/locations/global/workloadIdentityPools/github/providers/github
 # GCP_DEPLOYER_SA=github-deployer@<project>.iam.gserviceaccount.com

 Real prod secrets live in Secret Manager and are mounted as Cloud Run env vars by Terraform. .env is local-dev only.

 Migration Phases (each ends in a working state)

 1. pgvector locally — swap compose postgres image, add migration 003_pgvector.sql, port retrieval_service first, validate parity vs Qdrant on a sample query, port the rest, drop Qdrant from default
 compose. pytest -q passes.
 2. Production Dockerfiles — backend + frontend prod stages, Next standalone. Smoke test docker run locally.
 3. Terraform bootstrap — state bucket, APIs enabled, Artifact Registry, WIF pool, deployer SA. gcloud auth configure-docker + push first images.
 4. Cloud SQL + Secrets — terraform apply. Load schema via Cloud SQL Auth Proxy from laptop. Seed Scryfall once manually.
 5. Cloud Run backend (auth disabled, admin endpoints behind a feature flag) — verify /api/v1/health.
 6. Cloud Run frontend — verify SSR + /api/* proxy.
 7. Cloud Run Job + Scheduler — weekly sync; trigger once manually.
 8. Auth — Auth.js, schema migration 002_google_sub.sql, FastAPI dependency, gate routes, drop localStorage path. Re-deploy.
 9. GitHub Actions — .github/workflows/deploy.yml via WIF; auto build + deploy on main.
 10. Custom domain + lock down admin endpoints.

 Verification

 - gcloud run services describe mtg-backend --region=europe-west1 reachable; GET /api/v1/health returns 200.
 - psql via Cloud SQL Auth Proxy: SELECT count(*) FROM cards WHERE embedding IS NOT NULL; ≈ 22k.
 - Frontend URL: load homepage → Google Sign-In → Network tab shows session cookie, no mtg_helper_account_id in localStorage.
 - Cloud Logging: backend logs sub=… extracted from verified ID token.
 - Unauthenticated POST /api/v1/admin/sync-cards returns 401; from a non-admin email → 403.
 - Manually trigger sync: gcloud run jobs execute scryfall-sync --region=europe-west1 --wait → exit 0, row count grows.
 - Force scheduler: gcloud scheduler jobs run scryfall-weekly --location=europe-west1.
 - Cold-start test: wait 20 min, hit backend, response < 5s.
 - Cost sanity: GCP Billing report, project filter, daily ≈ €0.30–0.50.
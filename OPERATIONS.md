# Operations Runbook

Production deployment, source sync, and tracing. For project conventions see [AGENTS.md](AGENTS.md).
For local boot/tests and database safety, start with [VERIFY.md](VERIFY.md).

## Compose layout

The base file is local-dev only; production and publication staging are standalone stacks.

| File | Purpose |
|---|---|
| `docker-compose.staging.yml` | Isolated local Scryfall publication testing. Dedicated database volume, loopback-only ports, no working AI key. See [staging instructions](docs/scryfall-label-staging.md). |
| `docker-compose.yml` | Local dev. Postgres + backend (`--reload`) + frontend (`pnpm dev`). Source dirs bind-mounted for hot reload. Data in a Docker-managed named volume. |
| `docker-compose.live.yml` | Explicit override for local hot reload against shared live data; disables startup maintenance, not ordinary writes. Use with the base file. |
| `docker-compose.prod.yml` | Standalone production/Portainer stack. Connects to existing shared PostgreSQL, builds the production frontend, and runs daily `scryfall-sync` (weekly full source refresh/tagging). |

The production file intentionally does **not** use Compose merge tags (`!reset`, `!override`) so it
works with current Portainer Git stacks. It publishes only the frontend to
`127.0.0.1:${FRONTEND_PORT:-3001}` by default; point the homeserver's existing reverse proxy /
Cloudflare Tunnel there. The `scryfall-sync` cron is prod-only; locally you trigger card sync from
the Admin page when you want fresh data.

## Portainer setup summary

1. Ensure the existing PostgreSQL service is reachable on the external `shared_database` Docker
   network. Set `MTG_DATABASE_URL` to its DSN; this stack creates no database or data directories.

2. In Portainer, create a Git stack using:
   - Repository URL: this repo
   - Compose path: `docker-compose.prod.yml`
   - Branch: `main`
3. Add environment variables from `portainer.env.example` in the Portainer stack UI.
4. Enable automatic Git updates for the stack.
5. For immediate deploys on push, add the Portainer stack webhook URL as a repository `push` webhook.

## Local boot

Follow [VERIFY.md](VERIFY.md) for configuration, isolated/live mode switching, and safe tests.
Both `backend/.env` and root `.env` are needed for the documented signed-in local setup.
Root `.env` supplies Google credentials and a unique local session secret. Backend configuration
is runtime-only and is not copied into images. All published local ports bind to loopback.

Live-data mode is for schema-compatible development only: **normal edits affect production**.
Do not run schema experiments, repairs, global source refreshes, or destructive tests there.

## Prod boot with Portainer

1. On the homeserver, install Portainer Agent/CE and make sure the Docker host can build images.
2. Ensure the external `shared_database` Docker network and existing PostgreSQL service are
   available. Set `MTG_DATABASE_URL`; database storage is managed outside this stack.

3. In Portainer: **Stacks → Add stack → Git repository**.
   - Repository URL: this repo
   - Branch: `main`
   - Compose path: `docker-compose.prod.yml`
   - Environment variables: copy keys from `portainer.env.example` and fill secrets.
   - Leave `FRONTEND_BIND_ADDR=127.0.0.1` unless the tunnel/proxy runs on another host.
4. Deploy the stack.
5. Point the existing homeserver tunnel/proxy at `http://127.0.0.1:${FRONTEND_PORT}`.

After updating an existing stack, remove its obsolete vector-search container in Portainer
if it remains as an orphan. Preserve its old bind-mounted storage until a separate data cleanup
is approved; do not remove unrelated containers or database volumes.

Compose uses the stack environment only for interpolation and forwards each variable to the service
that needs it. In particular, `OPENAI_API_KEY` and the database DSN are available only to `backend`;
`frontend` receives only URL/auth settings, and `scryfall-sync` receives
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
  reply. Model/tool child spans retain detailed evidence and provider history. Background turns
  remain open until completion; failed turns record their error.
- HTTP start requests and SSE connections remain ordinary traces, not duplicate session turns.
  Each assistant turn links back to its initiating HTTP request.
- API callers can send `conversation_id` (a UUID) in both `POST /api/v1/decks/{deck_id}/coach` and
  `POST /api/v1/decks/{deck_id}/coach/start`. Reuse it for follow-ups and generate a new UUID when
  clearing chat history. Omit it for a standalone one-turn session; invalid UUIDs return 422.

Session grouping uses Assay's documented OpenTelemetry `session.id` root attribute and
`gen_ai.conversation.id` on GenAI spans, on the same provider as the rest of our tracing.
It does not load conversation history from Assay: the assistant receives bounded history from the
current chat page, not saved cross-chat memory. Old memory rows remain stored but are unused.
Existing traces are not retroactively grouped. Without Assay configuration, chat behavior is
unchanged and nothing exports.

## Database

Schema is `backend/src/mtg_helper/sql/schema.sql`, including idempotent upgrade statements.
The base local PostgreSQL container initializes it on first startup. Backend startup also calls
`apply_schema()` when `RUN_STARTUP_MAINTENANCE=true` (the default), along with catalog initialization
and deck identity repair. The live-data override disables that maintenance entirely.

There is no separate migration framework. Validate edits/upgrades against an isolated database
first; idempotence does not mean a schema edit is non-destructive or safe for live data.

```bash
# Isolated local mode only, after following VERIFY.md; never use the live override here.
docker compose restart backend

# psql shell
docker compose exec postgres psql -U mtg -d mtg_helper
```

### Production schema apply

Follow the [actual-data rehearsal, backup and verification procedure](docs/scryfall-publication-production.md)
before deploying schema changes. Do not restart production as a substitute for preservation checks
and a final backup. That release record describes the October 13 deployment, not current approval.

## Card data sync

Easiest: sign in as an admin user, click **Admin** in the nav (only visible to addresses listed in `ADMIN_EMAILS`), use the buttons. The page calls the same endpoints below.

Set the admin allowlist on the backend (`backend/.env` for local Compose, stack env for production):

```
ADMIN_EMAILS="you@example.com,other@example.com"
```

The frontend obtains `is_admin` from the current account; the backend enforces access.
Standalone staging uses root `ADMIN_EMAILS` as described in its own runbook.

Use **Refresh All** for the complete source-sync and rule-based tagging pipeline. It includes
Scryfall, MTGJSON, Moxfield and Archidekt; no separate indexing service is required.

```bash
TOKEN="<configured INTERNAL_API_TOKEN>"
BASE="http://localhost:8000"   # isolated local backend; never live-data development

curl -X POST -H "X-Internal-Token: $TOKEN" "$BASE/api/v1/admin/refresh-all"
```

For production internal jobs use `http://backend:8000` from the stack network, as the sync worker
does. The public frontend proxy requires a Google session; an internal token alone does not
authenticate through it. Do not expose the backend publicly to run maintenance.

For a Scryfall-only refresh, use `/api/v1/admin/sync-cards`; for rule-based tagging only,
use `/api/v1/admin/tag-cards`. Jobs run in the background; inspect `/api/v1/admin/status`
or the Admin UI for completion before starting dependent work.

Daily card auto-sync runs **only in prod** via `scryfall-sync` in `docker-compose.prod.yml`.
It runs full source sync and tagging on startup and every seventh day; intervening daily runs
only sync shared Scryfall facts/history. This does not run deck AI analysis. Locally, sync manually
from Admin. Backend startup also syncs when `cards` is empty.

### Experimental New Cards pilot

After a reviewed schema deployment, an existing populated database needs **one Admin card sync**
to bootstrap source data: startup does not silently redownload
its catalog. Discovery then publishes Oracle facts plus full Default Cards printing history in the
same transaction as canonical cards. Failed/truncated refreshes retain the previous catalog. Allow
additional temporary disk/network space for the compressed history (130 MiB download cap) and memory
for the existing Oracle export. No manual data migration or new credentials are needed.

Open a deck → **New Cards** to inspect its source date, coverage and complete Commander-Konstellation
result. Reads and status refreshes never make model calls. An administrator enables the global
automatic flag after a successful catalog publication, or explicitly starts one global run. Work is
shared by Commander-Konstellation, globally serial, and limited to 100 packages per UTC day by
default; each package contains at most eight cards with a 180 KB input cap, 7,000 output tokens, low
reasoning, no SDK retries, and a 90-second bound. A reserved provider attempt counts even when it
fails or is interrupted, and automatic retry waits until the next UTC day.

Advice is unverified: neither research evaluator passed trusted-recommendation acceptance. The pilot
shows exact source rules separately and excludes previews, unknown origins, promo-only originals and
unresolved special products. Original regular-product releases use the 60-day UTC window, not early
promos or later representative printings. Coverage is conservative, not a complete spoiler feed.

**Plan addition** is explicit and idempotent; it never edits physical cards or plans supporting swaps.
Only Commander facts and relevant candidate facts invalidate shared advice; deck contents, goals,
plans, prices and images do not. Pending additions are not support. Dismissals persist per account/deck; the UI can undo
the latest dismissal. Saved plans survive age expiry. Pilot-origin plans recheck current local
legality, color identity and copy limits during single/batch completion; failures roll back the whole
revision. Manual/Rule 0 plans retain existing policy. A stale catalog is visibly flagged after two
days; ask an admin to sync it rather than treating refresh-status as a sync button.

Testing a PR locally or opening it does **not** deploy this feature. Do not merge solely on mechanical
evidence checks: they verify identity/quotations, not MTG rules interpretation. Report deck goals,
card name, generated claim, source text and expected interaction when giving pilot feedback.

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

## Production stack CLI fallback

Prefer Portainer for normal deploys. If you need to manage the stack by SSH:

```bash
cd /opt/mtg-helper
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$COMPOSE ps
$COMPOSE logs -f backend
$COMPOSE restart backend
$COMPOSE up -d --build --force-recreate backend frontend
$COMPOSE down            # stops this stack; shared PostgreSQL and its storage are unaffected
```

## Database backups

Shared PostgreSQL storage and backups are managed outside this application stack. Verify its
backup/restore procedure before schema deployments; follow the
[preservation procedure](docs/scryfall-publication-production.md) for application data checks.

## Common deploy failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Backend container restart-loops after deploy | Schema apply error or missing env var | `$COMPOSE logs --tail=100 backend` on the homeserver |
| Sync endpoint returns 401 with `X-Internal-Token` | Missing/mismatched token between backend and caller | Compare configured secrets privately; never print environment files or full container configuration into logs/transcripts. |

## Development checks

Prepare the isolated test database using [VERIFY.md](VERIFY.md). These are development checks,
not a claim that CI runs every suite; the checked-in workflow targets the offline recommendation core.

```bash
# backend
cd backend
uv run ruff check . && uv run ruff format --check .
uv run ty check src/
uv run pytest -q

# frontend (Node 22; from backend/)
cd ../frontend
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

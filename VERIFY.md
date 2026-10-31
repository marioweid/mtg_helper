# Development verification

Run Compose commands from the repository root. **All application startup and verification run in
Docker Compose containers**, including tests, linters, type checks, and builds. A browser may access
the Compose-hosted UI. Production Portainer configuration is separate.

Check the daemon before doing anything else:

```powershell
docker info --format '{{.ServerVersion}}'
docker compose -f docker-compose.yml config --quiet
```

If Docker is not running, ask the user to start Docker and resume afterward. Do not substitute
host PostgreSQL, host servers, or host-run checks. Preserve existing Docker volumes and environment
files. Use `-f docker-compose.yml` explicitly so a live-data override is never selected implicitly.

Build the local images and start the local database:

```powershell
docker compose -f docker-compose.yml build backend frontend
docker compose -f docker-compose.yml up -d --wait postgres
```

## Routine verification: no Google login

**Do not require an interactive Google sign-in for ordinary code verification.** Backend
API tests use the real application with disposable accounts and test-only authentication
overrides from `backend/tests/conftest.py`. Auth tests supply synthetic provider claims;
frontend tests use synthetic sessions. The explicit local identity below is a running-app feature,
not a test override. Never copy Google tokens into tests or bypass production authentication.

Run backend checks from the repository root. This PowerShell helper mounts the complete checkout
read-only for tests that inspect repository files; the Linux virtualenv and pytest cache remain in
the disposable container, not the host checkout. Dependencies come from the existing frozen lock.

```powershell
function BackendCheck {
  docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e RUFF_CACHE_DIR=/tmp/ruff-cache -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --extra dev --frozen @args
  if ($LASTEXITCODE -ne 0) { throw 'Backend container verification failed.' }
}
BackendCheck pytest -q -W error -m no_db -o cache_dir=/tmp/pytest-cache
BackendCheck ruff check .
BackendCheck ruff format --check .
BackendCheck ty check src/
```

`-m no_db` matters: an unmarked test can initialize the database for the entire session,
even when other selected tests do not need it. These container checks need no OAuth or live model key.
For SQL/API behavior, use the isolated database checks below, also without a Google login.
Run affected suites, not just offline tests, when changing database-backed behavior.

Frontend checks from the repository root (Node 22 and dependencies live in the image):

```powershell
docker compose -f docker-compose.yml run --rm --no-deps -e LOCAL_DEV_AUTH=false frontend pnpm test
docker compose -f docker-compose.yml run --rm --no-deps -e LOCAL_DEV_AUTH=false frontend pnpm typecheck
docker compose -f docker-compose.yml run --rm --no-deps -e LOCAL_DEV_AUTH=false frontend pnpm lint
docker compose -f docker-compose.yml run --rm --no-deps -e LOCAL_DEV_AUTH=false frontend pnpm format:check
docker compose -f docker-compose.yml run --rm --no-deps -e LOCAL_DEV_AUTH=false frontend pnpm build
```

Start the interactive local application after isolated schema/tests have passed:

```powershell
docker compose -f docker-compose.yml up -d --wait backend frontend
docker compose -f docker-compose.yml exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

Expect `{"status":"ok"}`; open `http://localhost:3000`. A frontend build check runs in a
separate one-off container so it does not replace the running dev server's build output.

### Optional automatic local identity

For the isolated local stack, set `LOCAL_DEV_AUTH=true` and `LOCAL_DEV_ACCOUNT_ID` to an existing
local account UUID in the ignored **root `.env`**. Preserve all other values. List local account IDs
without printing credentials:

```powershell
docker compose -f docker-compose.yml exec -T postgres psql -U mtg -d mtg_helper -c "SELECT id, display_name FROM accounts ORDER BY created_at"
docker compose -f docker-compose.yml up -d --build --wait
```

Open `http://localhost:3000/decks`: no Google sign-in is needed and navigation says **Local
development**. The fixed account keeps its decks, collections, preferences and feature flags. No
account is created, merged or promoted to admin. An existing account with an email is required; a
missing account refuses startup. Keep ports bound to loopback and use the localhost origin above.

Both apps require the explicit local deployment; backend configuration and the actual connected
database must match the isolated Compose `postgres` / `mtg_helper` target. Remote/rerouted databases
and non-local deployment modes are refused. Cross-site browser mutations are rejected. Live,
staging and production Compose files force this mode off. Production frontend builds also run with
the opt-in off; frontend production runtime refuses it. This is not safe for a shared/public machine.

To return to Google login, set `LOCAL_DEV_AUTH=false` in root `.env` and recreate the local stack.
Do not clear cookies or rotate `AUTH_SECRET`; existing Google login/refresh behavior remains intact.
Tests always disable ambient local identity and enable it explicitly only in focused tests.

### Browser checks: reuse the session

- In explicit local identity mode, open the app directly; do not request Google sign-in for local
  browser checks. The rules below apply when checking normal Google authentication or live mode.
- Keep using the same browser profile, `http://localhost:3000` origin, and existing root
  `AUTH_SECRET`. Do not regenerate the secret, clear cookies, or sign out between checks.
- Reuse a signed-in tab/profile before requesting another login. The existing Auth.js
  implementation refreshes Google ID tokens using the stored refresh token; restarting the
  backend does not itself require Google consent again.
- Session cookies or browser storage snapshots are credentials. If retained by browser tooling,
  keep them outside version control (for example, ignored `.local/browser/`) and never print them.
- A first login, expired/revoked session, or failed refresh may still need human interaction.
  For unrelated cleanup/refactoring, finish automated verification and record authenticated
  browser smoke as pending instead of repeatedly asking the user to sign in.
- Test real OAuth/consent only when explicitly verifying authentication, or when a changed
  authenticated UI flow genuinely requires browser acceptance. Fixture tests are not OAuth E2E.

## Configuration

Preserve existing environment files. On a new checkout copy `backend/.env.example` to
`backend/.env`, and `.env.example` to root `.env` (PowerShell: `Copy-Item`). Set the
backend OpenAI key and root Google credentials plus a unique local Auth.js secret for the
interactive application. Automated tests use synthetic credentials and do not need real Google
credentials or a working model key. Create the local Auth.js secret once, then preserve it.
Live mode additionally requires `LIVE_DATABASE_URL` with a LAN-resolvable database host.
Reuse the existing production Google client only with approval. Its authorized redirect
must include `http://localhost:3000/api/auth/callback/google`. The backend client ID
automatically matches `AUTH_GOOGLE_ID`. A different Auth.js secret keeps local sessions separate.

Check ignored status without displaying values:

```sh
git check-ignore .env backend/.env
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.live.yml config --quiet
```

The last command fails if the live DSN is unset. Do not print the full rendered Compose
configuration or `docker inspect`: both can expose credentials. Examples contain no real secrets.

## Live-data mode

**Normal writes affect the hosted application immediately.** This is not a sandbox.
Use it for schema-compatible refactors. Schema/migration changes must first be tested
on the isolated database before commit/deployment. Do not manually run global admin
refreshes, migrations, repairs, schema scripts, or destructive tests against live data.
Paid model calls use the reused OpenAI account and are not part of these checks.

Build and check connectivity without starting the backend or running its lifespan:

```sh
docker compose -f docker-compose.yml -f docker-compose.live.yml build backend frontend
docker compose -f docker-compose.yml -f docker-compose.live.yml run --rm --no-deps backend uv run --no-sync python scripts/check_database.py
```

The checker uses a read-only transaction. Expect database `mtg_app`, role `mtg_app`, and
existing deck/account/collection counts. It never prints the DSN or individual records.
Fix LAN access or credentials before proceeding if this fails.

```sh
docker compose -f docker-compose.yml -f docker-compose.live.yml up -d --no-build
curl http://localhost:8000/health
```

Expect `{"status":"ok"}`. If a signed-in browser session is already available at
`http://localhost:3000`, compare an existing deck and collection without editing them.
Reuse the session for the same Google account as the hosted application; do not request fresh
consent for every restart. If unavailable, record authenticated browser verification as pending
and continue with automated checks. OAuth redirect problems require the localhost callback in
Google Cloud; do not bypass running-app authentication.

```sh
docker compose -f docker-compose.yml -f docker-compose.live.yml restart backend
curl http://localhost:8000/health
docker compose -f docker-compose.yml -f docker-compose.live.yml logs --tail=30 backend
```

Expect health OK and a startup-maintenance-disabled warning; no initial sync or repairs.
Source edits to backend `src` and frontend `app`, `lib`, `components`, `auth.ts`, and
`middleware.ts` hot reload. Package/config changes can still require rebuilding.

## Isolated database mode and tests

Switch modes explicitly; a plain restart does not change container environment:

```sh
docker compose -f docker-compose.yml -f docker-compose.live.yml down
docker compose -f docker-compose.yml up -d --build
```

The base backend connects only to local PostgreSQL and retains normal startup maintenance.
Its empty card catalog can trigger an initial external catalog download. Root live credentials
are not selected without the override. Local schema changes and schema experiments stay here.

For tests start only the local database. Create the test database once (skip `createdb`
if it already exists). Do not change the fixed local `TEST_DATABASE_URL` to a live DSN.

```sh
docker compose -f docker-compose.yml up -d --wait postgres
docker compose -f docker-compose.yml exec -T postgres createdb -U mtg mtg_helper_test
docker compose -f docker-compose.yml run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q tests/test_accounts.py tests/test_deck_crud.py
```

Test setup drops/recreates the test schema. It rejects remote hosts, non-test names,
query-parameter routing overrides, and the application's database before connecting.
Tests never call paid models or require the homeserver when using this local target.
The `client` fixture creates its own test account, so API/deck/collection/ownership checks do
not require a real browser, Google credentials, or the production account. The test override
is not enabled in Compose or production.

For repository-aware integration checks, use `BackendCheck` from the routine verification section:

```powershell
BackendCheck pytest -q -W error tests/test_accounts.py tests/test_deck_crud.py -o cache_dir=/tmp/pytest-cache
```

The container target is the Compose `postgres` service and disposable `mtg_helper_test` database.
Keep that target separate from the application database. Docker being unavailable blocks
verification until the user starts it; it does not authorize a host database fallback.

If testing inside live-mode containers, use the same Compose override on `run`/`exec`;
`TEST_DATABASE_URL` still selects the isolated local `_test` database, never the live application.

## Stop/reset

Use `docker compose down` (include the override when operating live mode) to stop local
containers. Do not use `down -v` as routine cleanup: it deletes local database volumes.
Neither mode's stop command changes homeserver containers. Never reset shared data.

## Existing copied data

Preserve earlier isolated copied databases; they are not a host verification fallback. Normal
development uses the local Compose stack and disposable test accounts. A new private-data export
or attaching an existing copied database needs its own reviewed, Docker-based procedure and explicit
authorization. Starting Compose or verifying Discover does not authorize reading or copying live data.

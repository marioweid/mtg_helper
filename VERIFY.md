# Development verification

Run Compose commands from the repository root. Production Portainer configuration is
separate; these commands operate on the local project only. Host checks need `uv` and Node 22.
Container workflows need Docker Desktop with Linux containers and Compose; SQL tests can also
use a separate local PostgreSQL 16 instance.

## Routine verification: no Google login

**Do not require an interactive Google sign-in for ordinary code verification.** Backend
API tests use the real application with disposable accounts and test-only authentication
overrides from `backend/tests/conftest.py`. Auth tests supply synthetic provider claims;
frontend tests use synthetic sessions. None of this changes running-app authentication.
Do not add a production auth bypass or copy Google tokens into tests to avoid signing in.

Start with the offline checks from `backend/`:

```sh
uv run pytest -q -W error -m no_db
uv run ruff check .
uv run ruff format --check .
uv run ty check src/
```

`-m no_db` matters: an unmarked test can initialize the database for the entire session,
even when other selected tests do not need it. Offline checks need neither Docker nor OAuth.
For SQL/API behavior, use the isolated database checks below, also without a Google login.
Run affected suites, not just offline tests, when changing database-backed behavior.

Frontend checks from `frontend/` (Node 22, dependencies already installed):

```sh
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

If `pnpm` is not on PATH, use the installed tools directly rather than skipping checks:

```sh
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc --noEmit
node_modules/.bin/oxlint app lib components
node_modules/.bin/oxfmt --check .
node node_modules/next/dist/bin/next build
```

On PowerShell, invoke oxlint and oxfmt as `& .\node_modules\.bin\oxlint.cmd` and
`& .\node_modules\.bin\oxfmt.cmd`, with the same arguments.

### Browser checks: reuse the session

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
docker compose config --quiet
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
docker compose up -d --build
```

The base backend connects only to local PostgreSQL and retains normal startup maintenance.
Its empty card catalog can trigger an initial external catalog download. Root live credentials
are not selected without the override. Local schema changes and schema experiments stay here.

For tests start only the local database. Create the test database once (skip `createdb`
if it already exists). Do not change the fixed local `TEST_DATABASE_URL` to a live DSN.

```sh
docker compose up -d --wait postgres
docker compose exec postgres createdb -U mtg mtg_helper_test
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q tests/test_accounts.py tests/test_deck_crud.py
```

Test setup drops/recreates the test schema. It rejects remote hosts, non-test names,
query-parameter routing overrides, and the application's database before connecting.
Tests never call paid models or require the homeserver when using this local target.
The `client` fixture creates its own test account, so API/deck/collection/ownership checks do
not require a real browser, Google credentials, or the production account. The test override
is not enabled in Compose or production.

For host-side integration tests against that same disposable database, run from `backend/`:

```sh
uv run pytest -q -W error tests/test_accounts.py tests/test_deck_crud.py
```

The host default is `127.0.0.1`/`localhost:5432`, database `mtg_helper_test`. If using a
different local PostgreSQL 16 instance, explicitly set `TEST_DATABASE_URL` to its disposable
`_test` database. Bind any temporary test server to loopback and use an empty, dedicated cluster;
do not repurpose existing application clusters. Docker being unavailable blocks container checks,
not offline tests or a separately available isolated PostgreSQL instance.

If testing inside live-mode containers, use the same Compose override on `run`/`exec`;
`TEST_DATABASE_URL` still selects the isolated local `_test` database, never the live application.

## Stop/reset

Use `docker compose down` (include the override when operating live mode) to stop local
containers. Do not use `down -v` as routine cleanup: it deletes local database volumes.
Neither mode's stop command changes homeserver containers. Never reset shared data.

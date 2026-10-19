# Development verification

Run Compose commands from the repository root. Production Portainer configuration is
separate; these commands operate on the local project only. Requirements: Docker Desktop
with Linux containers, Compose, and `uv` for host-side Python checks.

## Configuration

Preserve existing environment files. On a new checkout copy `backend/.env.example` to
`backend/.env`, and `.env.example` to root `.env` (PowerShell: `Copy-Item`). Set the
backend OpenAI key and root Google credentials plus a unique local Auth.js secret.
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

Expect `{"status":"ok"}`. Open `http://localhost:3000` and sign in with the same Google
account as the hosted application. Compare an existing deck and collection without editing
them. An OAuth redirect mismatch requires adding the localhost callback in Google Cloud;
do not bypass authentication. If sign-in needs human interaction, record that validation as pending.

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

Focused safety checks need no database (run from `backend/`):

```sh
uv run pytest -q tests/test_live_development.py tests/test_observability.py
uv run ruff check .
uv run ruff format --check .
uv run ty check src/
```

If testing inside live-mode containers, use the same Compose override on `run`/`exec`;
`TEST_DATABASE_URL` still selects the isolated local `_test` database, never the live application.

## Stop/reset

Use `docker compose down` (include the override when operating live mode) to stop local
containers. Do not use `down -v` as routine cleanup: it deletes local database volumes.
Neither mode's stop command changes homeserver containers. Never reset shared data.

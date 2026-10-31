# MTG Helper — Project Conventions

## Stack

- **Backend:** Python 3.13, FastAPI, asyncpg (plain SQL, no ORM), Pydantic V2, uv
- **Frontend:** Next.js 14+ (App Router), TypeScript
- **Database:** PostgreSQL 16
- **AI:** OpenAI GPT API via OpenAI SDK
- **Local dev:** Docker Compose

## Python

- Runtime: 3.13, managed with `uv`
- Lint + format: `ruff check` / `ruff format`
- Types: `ty check`
- Tests: `pytest -q` in the backend Compose container

## Verification: Docker only

- Build, boot, test, lint, type-check, and verify formatting in Docker Compose containers.
  Browser checks target the Compose-hosted application. Read `VERIFY.md` for exact commands.
- Check the Docker daemon first. If it is unavailable, ask the user to start Docker; they may
  simply have forgotten. Resume once available instead of launching host-side replacements.
- Use the explicit local `docker-compose.yml` by default. Host PostgreSQL, uvicorn, Node/pnpm,
  or host-run test suites are not verification fallbacks. Never select live mode implicitly.
- Automatic local identity is an explicit isolated-Compose feature, not a test auth bypass.
  Preserve its deployment/database guards and existing account ownership; see `VERIFY.md`.

## Code constraints

- ≤100 lines per function, cyclomatic complexity ≤8
- ≤5 positional parameters
- 100-char line length
- Absolute imports only
- Google-style docstrings on non-trivial public APIs

## Database

- All SQL is plain asyncpg with `$1, $2` positional params — never f-string SQL values
- Schema lives in `backend/src/mtg_helper/sql/schema.sql`
- Auto-initialized via `docker-entrypoint-initdb.d/` on first `docker compose up`
- Read `VERIFY.md` before booting, testing, or changing database configuration.
- Live-data mode is for schema-compatible refactors; normal edits affect production.
- Validate schema changes and migrations on the isolated local database before committing
  or deploying. Keep live-mode startup maintenance disabled.
- Run destructive tests only against the disposable local `_test` database. Never point
  `TEST_DATABASE_URL`, schema resets, repairs, or migration experiments at shared live data.

## API design

- All responses use `DataResponse[T]` envelope with optional `PaginationMeta`
- All errors use `ErrorResponse` with `code` and `message`
- Base path: `/api/v1`

## Environment variables

Loaded via pydantic-settings from `.env` in `backend/`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | asyncpg DSN |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `SCRYFALL_BULK_DATA_URL` | `https://api.scryfall.com/bulk-data` | Bulk data endpoint |

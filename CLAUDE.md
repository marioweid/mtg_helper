# MTG Helper — Project Conventions

## Stack

- **Backend:** Python 3.13, FastAPI, asyncpg (plain SQL, no ORM), Pydantic V2, uv
- **Frontend:** Next.js 14+ (App Router), TypeScript
- **Database:** PostgreSQL 16
- **AI:** Claude API via Anthropic SDK
- **Local dev:** Docker Compose

## Python

- Runtime: 3.13, managed with `uv`
- Lint + format: `ruff check` / `ruff format`
- Types: `ty check`
- Tests: `pytest -q` from `backend/`

```bash
cd backend
uv run ruff check .
uv run ruff format .
uv run ty check src/
uv run pytest -q
```

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

## API design

- All responses use `DataResponse[T]` envelope with optional `PaginationMeta`
- All errors use `ErrorResponse` with `code` and `message`
- Base path: `/api/v1`

## Environment variables

Loaded via pydantic-settings from `.env` in `backend/`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | asyncpg DSN |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `SCRYFALL_BULK_DATA_URL` | `https://api.scryfall.com/bulk-data` | Bulk data endpoint |

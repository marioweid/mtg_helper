# Architecture

```text
Browser -> Next.js / Auth.js -> FastAPI -> PostgreSQL
                                  |-> OpenAI Responses API
                                  |-> Scryfall bulk exports
                                  |-> MTGJSON / Moxfield / Archidekt / Commander Spellbook
                                  `-> optional Assay tracing
```

## Frontend and authentication

`frontend/app/` contains the App Router pages; shared UI and client request/state code
live in `frontend/components/` and `frontend/lib/`. Auth.js handles Google sign-in.
The same-origin API proxy (`frontend/app/api/[...path]/route.ts`) forwards the Google
ID token to FastAPI. Backend auth verifies it and resolves the current account.

## Backend boundaries

Paths below are relative to `backend/src/mtg_helper/`:

| Area | Responsibility |
|---|---|
| `routers/`, `models/` | HTTP routes and typed request/response contracts |
| `services/deck_service.py`, `services/planned_change_service.py`, `services/revision_service.py` | Physical cards, pending changes, atomic revisions |
| `services/ai_service.py`, `services/retrieval_service.py` | Deterministic stage suggestions using local search and community evidence; no model call for stage generation |
| `services/assistant_service.py`, `services/mtg_assistant.py`, `services/mtg_assistant_tools.py` | Authorized/traced Coach turns and one tool-using assistant |
| `services/agents/` | Shared OpenAI model settings and focused describe/extract/commander/doctor agents |
| `services/new_cards/` | Released-card discovery, physical-deck assessments, dismissals, and planning |
| `services/recommendations/` | Shared source-backed search/evidence core and default-off Discover adapter |
| `services/scryfall.py`, `services/scryfall_tags.py`, `services/scryfall_tag_repository.py` | Validated card/history/tag publication |
| `observability.py` | Optional private Assay traces and per-chat correlation |
| `sql/schema.sql` | Tables, views, indexes, and idempotent schema upgrades |

AI output is advisory. Explicit user actions add cards or plans; completion revalidates
experimental-origin additions. Coach history comes from bounded client-provided chat
history, not saved cross-chat memory or Assay. Retired personalization tables remain stored.

## Data and execution

PostgreSQL is the only application datastore; access uses asyncpg and parameterized SQL.
Card images use Scryfall CDN URLs. Legacy retrieval still uses rule-derived labels and
community evidence. Canonical Scryfall tag publication exists, but consumer cutover is
[unfinished](../../docs/scryfall-only-label-migration-plan.md).

Coach/optimizer/admin job registries are process-local. New Cards has durable account leases
and quotas with background execution. Discover persists runs, single-use paid attempts,
spending reservations, and immutable source snapshots; interrupted calls are not auto-retried.

## Runtime layout

- Local Compose runs frontend, backend, and isolated PostgreSQL with source hot reload.
- The explicit live-data override connects the backend to shared data and disables startup
  maintenance, **not ordinary application writes**. See [VERIFY.md](../../VERIFY.md).
- Production Compose runs frontend/backend and a sync worker against external shared PostgreSQL,
  managed through Portainer and the existing reverse proxy. See [OPERATIONS.md](../../OPERATIONS.md).

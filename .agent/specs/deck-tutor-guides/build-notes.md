# Build notes: deck-tutor-guides round 2

## Changed files

- `backend/src/mtg_helper/models/tutor.py`: added typed Tutor setup, guide, evidence, run, and state contracts.
- `backend/src/mtg_helper/routers/tutor.py`: added authenticated owner-scoped Tutor setup, state, and manual-guide routes.
- `backend/src/mtg_helper/services/tutor/__init__.py`: added the Tutor service package.
- `backend/src/mtg_helper/services/tutor/evidence.py`: captures frozen exact local card facts and stable teaching identity hashes.
- `backend/src/mtg_helper/services/tutor/repository.py`: persists setup, idempotent durable runs, freshness, publication, and interruption recovery.
- `backend/src/mtg_helper/services/tutor/service.py`: orchestrates explicit bounded Commander/cEDH guide generation.
- `backend/src/mtg_helper/services/tutor/teaching.py`: supplies typed bounded model output and actual-list teaching instructions.
- `backend/src/mtg_helper/services/tutor/commander.py`: added the Commander teacher adapter.
- `backend/src/mtg_helper/services/tutor/cedh.py`: added the cEDH teacher adapter.
- `backend/src/mtg_helper/sql/schema.sql`: added additive, cascade-safe Tutor setup/run storage.
- `backend/src/mtg_helper/main.py`: registered Tutor routes and marks in-flight runs interrupted after restart.
- `backend/tests/test_tutor_guides.py`: added real SQL/FastAPI mode persistence and composition-freshness tests with a deterministic teacher.
- `frontend/components/tutor-panel.tsx`: added accessible Tutor mode setup, explicit generation, polling, status, warnings, and historical-guide display.
- `frontend/components/tutor-panel.test.tsx`: added Tutor empty/historical rendering tests.
- `frontend/lib/api.ts`: added Tutor client requests.
- `frontend/lib/types.ts`: added Tutor client contracts.
- `frontend/app/decks/[id]/page.tsx`: added the Tutor deck-workspace tab.
- `backend/src/mtg_helper/main.py`: applies the normal schema upgrade before recovering Tutor runs.
- `backend/src/mtg_helper/models/tutor.py`: retains pinned rules and source-reported combo line facts.
- `backend/src/mtg_helper/services/tutor/evidence.py`: aggregates Oracle quantities across printings,
  captures ordered commander identities, and records exact rules/combo availability and provenance.
- `backend/src/mtg_helper/services/tutor/repository.py`: checks the newly saved Tutor-Modus before
  publication and avoids external-source reads for state/freshness checks.
- `backend/src/mtg_helper/services/tutor/teaching.py`: supplies retained source status, rules, and
  verified line dependencies/outlets to the specialized teachers.
- `backend/tests/test_tutor_guides.py`: adds real Tutor HTTP/SQL coverage for printing-only splits
  and a mode change during blocked generation.

## Verification

- Docker daemon `29.5.3`; `docker compose -f docker-compose.yml config --quiet` passed.
- `BackendCheck pytest -q -W error tests/test_tutor_guides.py tests/test_deck_crud.py -o cache_dir=/tmp/pytest-cache`: **21 passed**.
- `BackendCheck pytest -q -W error tests/test_tutor_guides.py -o cache_dir=/tmp/pytest-cache`: **3 passed**.
- Backend Docker `ruff check .`, `ruff format --check .`, and `ty check src/`: **passed**.
- Frontend Docker `pnpm test`: **30 files, 125 tests passed**.
- Frontend Docker `pnpm typecheck`, `pnpm lint`, `pnpm format:check`, and `pnpm build`: **passed**.
- Focused red/green: `BackendCheck pytest -q -W error tests/test_tutor_guides.py -k printing
  -o cache_dir=/tmp/pytest-cache` failed before the aggregate fix and then passed (**1 passed**).
- `BackendCheck pytest -q -W error tests/test_tutor_guides.py -o cache_dir=/tmp/pytest-cache`:
  **5 passed**.
- `BackendCheck pytest -q -W error tests/test_tutor_guides.py tests/test_deck_crud.py
  tests/test_card_identity_service.py tests/test_snapshots.py tests/test_retrieval_source_tags.py
  -o cache_dir=/tmp/pytest-cache`: **41 passed**.
- Docker startup check `docker compose -f docker-compose.yml build backend frontend && docker compose
  -f docker-compose.yml up -d --wait postgres backend frontend`: green; subsequent in-container health
  request returned `{"status":"ok"}`.
- Final backend Docker ruff/format/type command: **All checks passed**; final frontend Docker gate:
  **30 files / 125 tests passed**, typecheck, lint, format and build passed.

## Deviation and blocker

- No `make gate` target exists; verification used the explicit Docker-only commands in `VERIFY.md`.
- A full backend `pytest -q -W error` was attempted and cannot be green in this checkout: its first
  failure after 96 passing tests is pre-existing `tests/test_buylist.py::test_buylist_reports_partial_owned_deficit`
  (expected `3 Sol Ring`, received empty output). It is outside the approved Tutor slice and was not changed.
  The full run also exceeded 10 minutes while reporting additional pre-existing failures, so it was stopped.
- Browser/live-model acceptance remains pending: no live model call or authenticated local-browser fixture was run.
- The slice intentionally retains self-contained frozen local card facts and explicit unavailable-source warnings;
  it does not add the non-goal reference, chat, or practice storage/interfaces.
- Browser and configured-live-model fixture runs remain pending: this repair round made no paid model request.

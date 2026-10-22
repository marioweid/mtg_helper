# Build notes — round 1

- `backend/src/mtg_helper/models/new_cards.py`: removes the retired quota status from the response contract.
- `backend/src/mtg_helper/routers/admin.py`: accepts only the global automation switch and rejects retired budget fields.
- `backend/src/mtg_helper/services/new_cards/service.py`: replaces quota/day scheduling with durable run tokens, serial claims, retry isolation, and generation-triggered automatic runs.
- `backend/src/mtg_helper/sql/schema.sql`: migrates legacy quota state to run/claim attempt tokens and drops the obsolete per-account jobs table.
- `backend/tests/conftest.py`: resets the revised durable New Cards run state.
- `backend/tests/test_new_cards_automation.py`: adds the AC07 801-card regression proving no 100-package cutoff and aligns automation selectors with the new control contract.
- `backend/tests/test_new_cards_pilot.py`: removes obsolete deck-analyze/quota workflow tests.
- `backend/tests/test_new_cards_personalization_removal.py`: removes obsolete deck-context cache tests superseded by shared Commander-Konstellation coverage.
- `frontend/components/admin-new-cards-panel.tsx`: removes budget/reset controls from global administration.
- `frontend/components/admin-new-cards-panel.test.tsx`: verifies the safe control panel exposes no budget UI.
- `frontend/components/new-cards-panel.tsx`: removes the quota wait state from deck results.
- `frontend/components/new-cards-panel.test.tsx`: removes the retired quota state assertion.
- `frontend/lib/types.ts`: removes the retired quota status literal.
- `OPERATIONS.md`, `docs/new-cards-pilot-contract.md`, `docs/new-cards-pilot-checks.md`: document delta-driven runs without quotas.

## Verification

```text
backend: uv run ruff check .                 All checks passed
backend: uv run ruff format --check .        232 files already formatted
backend: uv run ty check src/                All checks passed
backend: uv run pytest -q -W error -m no_db  530 passed, 787 deselected
frontend: vitest                             23 files, 114 tests passed
frontend: tsc / oxlint / oxfmt               no errors or warnings; formatted
frontend: next build                         succeeded
```

The required isolated PostgreSQL AC run could not execute: localhost:5432 refused connections and
Docker Desktop's `docker_engine` pipe was unavailable. No live data or paid transport was used.

## Deviations

None. The database-dependent AC selectors remain blocked by the unavailable disposable test database.

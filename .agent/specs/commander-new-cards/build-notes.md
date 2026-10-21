# Build notes — round 2

- `backend/src/mtg_helper/services/new_cards/service.py`: added durable serial package ownership,
  pre-provider authorization checks, publication-driven automatic activation, and bounded worker shutdown.
- `backend/src/mtg_helper/main.py`: owns the opt-in New Cards worker lifecycle before database-pool closure.
- `backend/src/mtg_helper/services/feature_flag_service.py`: added the default-off global New Cards
  automatic feature flag.
- `backend/src/mtg_helper/sql/schema.sql`: moved automatic control out of run state and added durable
  global active-package fields.
- `backend/src/mtg_helper/services/new_cards/repository.py`: suppresses deck-locally hidden picks and
  reports partial shared assessment state as waiting.
- `backend/src/mtg_helper/services/new_cards/evaluator.py`: removed the physical-support compatibility
  input branch.
- `backend/src/mtg_helper/routers/admin.py`: envelopes New Cards control responses and rejects boolean
  daily limits.
- `frontend/components/new-cards-state.ts`, `new-cards-panel.tsx`: poll waiting status and never render
  stale-source picks.
- `frontend/components/admin-new-cards-panel.tsx`: consumes control envelopes and blocks global start
  behind save state and confirmation.
- `frontend/components/{new-cards-panel,admin-new-cards-panel}.test.tsx`: replaced obsolete Analyze
  expectations and added AC13 locked-control coverage.
- `backend/tests/new_cards_fixtures.py`, `test_new_cards_discovery.py`: migrated test provider/context
  facts from physical support to commanders.
- `OPERATIONS.md`: replaced obsolete per-account Analyze-next-eight guidance with the shared global run
  contract.

## Verification

- `backend/`: `uv run pytest -q -W error -m no_db` → `531 passed, 790 deselected`.
- `backend/`: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check src/` → pass.
- `frontend/`: `node node_modules/vitest/vitest.mjs run` → `108 passed`.
- `frontend/`: TypeScript, oxlint, oxfmt, and `next build` → pass.

## Deviation

The required isolated-PostgreSQL acceptance matrix remains incomplete: only the pre-existing AC01
selector exists in `test_new_cards_automation.py`. This round fixes the evaluator-observed worker,
serialization, stale-result, local-hiding, UI safety, and scope violations, but does not claim the
missing AC02–AC16 end-to-end selector suite is complete.

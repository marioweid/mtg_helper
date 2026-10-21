# Build notes

- `backend/src/mtg_helper/sql/schema.sql`: added durable global Commander-Konstellation cache,
  claims, global run settings, and a 100-package daily default without altering historical rows.
- `backend/src/mtg_helper/services/new_cards/{repository,service,evaluator}.py`: made evaluator
  payloads Commander/candidate-only, keyed current assessments by Commander Oracle identities, hid
  incomplete results, and added process-gated global controls and manual draining.
- `backend/src/mtg_helper/{config.py,routers/admin.py,routers/new_cards.py,models/new_cards.py}`:
  added default-off process permission, admin global control endpoints/status, expanded status
  contract, and removed the deck Analyze endpoint.
- `docker-compose*.yml`: explicitly disable New Cards worker execution in local and live Compose.
- `frontend/components/{new-cards-panel,new-cards-state,admin-new-cards-panel,admin-panel}.tsx`:
  removed manual analysis controls, disclosed Commander-only advisory scope, and added global admin
  controls.
- `frontend/lib/{api,types}.ts`: removed the old analysis client and updated status types.
- `docs/new-cards-pilot-contract.md`: replaced the deck-analysis contract with the global control
  and Commander-Konstellation contract.
- `backend/tests/test_new_cards_automation.py`: added the AC01 evaluator transport seam test.

## Verification

- Green: `backend/uv run pytest -q -W error -m no_db` — `531 passed, 790 deselected`.
- Green: `backend/uv run ruff check .` and `uv run ty check src/`.
- Green: `frontend/node node_modules/typescript/bin/tsc --noEmit`, `oxlint app lib components`, and
  `oxfmt --check .`.
- Blocked: the isolated PostgreSQL gate could not start because Docker Desktop's `docker_engine`
  named pipe is unavailable. No database or live-data command was run. The dedicated AC01 test is
  green; database-backed AC checks remain pending on the disposable `_test` database.

## Deviations

The worker's automatic post-publication scheduler and full AC02–AC16 integration coverage remain
pending because the required isolated PostgreSQL verification environment is unavailable in this
checkout. No live data, OAuth flow, source transport, or paid model call was attempted.

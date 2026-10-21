# Build notes — round 3

- `backend/src/mtg_helper/services/new_cards/repository.py`: hides all cached picks when sources are stale.
- `backend/src/mtg_helper/services/new_cards/service.py`: continues past unavailable constellations, completes successive packages, snapshots automatic-day constellations, and stops automatic claims when disabled.
- `backend/tests/conftest.py`: resets New Cards durable state between isolated database tests.
- `backend/tests/new_cards_fixtures.py`: enables the worker and starts an explicit manual run only in New Cards integration fixtures.
- `backend/tests/test_new_cards_automation.py`: adds real PostgreSQL/evaluator-worker acceptance selectors AC01–AC11 and AC14–AC16.
- `backend/tests/test_new_cards_completion.py`: aligns the deck-local hiding expectation with shared eligible-card counts.
- `frontend/components/admin-new-cards-panel.tsx`: blocks starts after failed control requests and splits the panel into bounded components.
- `frontend/components/new-cards-panel.test.tsx`: adds AC12 state-rendering coverage without an analysis action.

## Verification

Green required checks:

```text
backend: uv run pytest -q -W error -m no_db                 530 passed, 804 deselected
backend: uv run ruff check .                                All checks passed
backend: uv run ruff format --check .                       234 files already formatted
backend: uv run ty check src/                               All checks passed
backend: uv run pytest -q -W error tests/test_new_cards_automation.py
         14 passed
frontend: vitest / tsc / oxlint / oxfmt / next build        115 passed; no warnings; build succeeded
AC selectors: backend 14 passed; AC12 7 passed; AC13 1 passed
```

The full backend suite was attempted. It remains red on pre-existing out-of-scope buylist behavior
(`tests/test_buylist.py::test_buylist_reports_partial_owned_deficit`); this round did not alter it.

## Deviations

None. The full-suite buylist failure is recorded as an unrelated blocker rather than changing unrelated code.

# Build notes — round 2

## Changed

- `backend/src/mtg_helper/sql/schema.sql`: added an append-only assessment-history table so superseded New Cards cache rows remain historical data.
- `backend/src/mtg_helper/services/new_cards/service.py`: archives a prior assessment before publishing changed-context advice.
- `backend/tests/conftest.py`: resets the new assessment-history fixture table between disposable-database tests.
- `backend/tests/test_assistant_personalization_removal.py`: uses captured deterministic provider requests to exercise real Assistant and Doctor orchestration, history, and progress without a business-logic mock.
- `backend/tests/test_retired_personalization_api.py`: uses authenticated, seeded deck/account HTTP checks for retired routes, retained account operations, and real Assistant response fields.
- `backend/tests/test_new_cards_personalization_removal.py`: verifies legacy notes/preferences neither affect New Cards fingerprints nor reach its captured provider request, and that a replaced old cache row is archived.
- `backend/tests/test_personalization_data_retention.py`: seeds/snapshots inactive tables and unrelated records across two schema applications, and guards repeated New Cards reads from legacy-table access.
- `backend/tests/test_deck_fit_service.py`: marks deterministic fit coverage database-free and verifies pet cards receive no special protection.
- `frontend/components/personalization-removal.test.tsx`: adds the required frontend deliverable covering absent retired Builder API methods and retained explicit Reject rendering.

## Verification

- `backend/`: `uv run pytest -q -W error -m no_db` → `522 passed, 792 deselected`.
- `backend/`: `uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `239 files already formatted`; `uv run ty check src/` → `All checks passed!`.
- `frontend/`: `corepack pnpm lint` → `0 warnings and 0 errors`; `corepack pnpm typecheck` → passed; `corepack pnpm test` → `22 passed`, `108 passed`; `corepack pnpm build` → production build passed.
- No `Makefile` or named gate command exists. The isolated database acceptance selection remains blocked before test setup because local PostgreSQL/Docker is unavailable (`ConnectionRefusedError: [WinError 1225]`). No shared/live DSN, environment file, or database was changed.

## Deviations

- Isolated database and browser validation remain blocked by the unavailable Docker daemon. The new database tests are committed but have not been passed locally; no substitution with live data was attempted.
- The round fixes only eval-1 FAIL/UNVERIFIED and VIOLATES feedback. Existing unrelated live-database development changes remain untouched.

# Build notes — round 3 continuation

## Current changes

- Fixed authenticated retired-memory HTTP checks to use `client.request` for GET/PUT.
- Replaced recommendation signature/source stubs with seeded before/after comparisons of
  real Builder, free-form, mana, swap, deck-fit, New Cards, and Discover outcomes.
- Restored Assistant background progress/tracing, recoverable provider failure, delayed
  completion, and uncaught progress-transport failure checks without restoring memory.
- Removed the frontend's leftover resolved `memory` mode. Page/action module checks now
  execute real Assistant follow-ups and Builder rejection/exclusion with test adapters.
- Fixed ineffective negative network matchers to `toContainEqual`; temporarily restoring
  retired memory/feedback fetches made both page/action checks fail at the corrected guards.
- Builder checks run queued mount effects and wait for suggestions; Preferences checks render
  the real navigation link, exact empty-state copy, no settings controls, and no requests.
- Removed two unused personalization parameters from exclusion helpers and their callers;
  ownership checks remain. Independent source reviewer verified both fixes.
- Removed saved-memory fields from the current evaluation schema/corpus, moving retained
  budget/theme/no-combo constraints into explicit current requests. Updated operational docs.
- Corrected three formatting-only blank-line leftovers in feature-modified frontend files.
- Fixed collection-order-sensitive New Cards fixtures: moved transport/model/pilot setup
  into `tests/new_cards_fixtures.py` and registered it in root conftest before collection.
  Removed test-module plugin registration and cross-test fixture aliases. The original
  failing order and its reverse both pass independently, without weakening assertions.

## Verification and limits

See `gate-3.md` and `eval-4.md`/`eval-5.md` for final commands and independent evidence.
The final main-run offline suite passes **527 tests**; all backend/frontend static gates,
**108 frontend tests**, and the frontend production build pass. The broader isolated
backend regression selection passes **226 tests**. Named backend acceptance independently
passes **42 tests**; the expanded acceptance/shared-fixture selection passes **74 tests**.
Both fixture orderings pass independently. Ruff reports **240 files formatted** after extraction.

All destructive tests used VERIFY's local disposable `_test` database. Existing legacy
personalization data and unrelated live-development work were preserved. No env files,
shared/live schema/data, auth middleware, or paid model configuration was changed.

User first approved temporary local OAuth-client reuse, then explicitly selected **Skip
manual checks** when the Review-pane browser had no authenticated session. Manual protected
UI acceptance remains deferred. The temporary frontend process tree was stopped; no browser
session or application listener remains from that attempt. PostgreSQL used for tests was
stopped without deleting volumes. Framework adapters/static markup
are not a claim of React hydration, Next routing, OAuth, or authenticated browser verification.

User requested feature-only commit/push after verification; unrelated live-development work
and generated diagnostic artifacts are excluded. Earlier feature commits remain intact.
Spec status is `blocked` only for deferred full-browser acceptance, not an unresolved
automated defect. The final independent automated verdict is PASS with no outstanding findings.

## Historical round 2 notes

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

# Build notes — round 1

## Round 2 checkpoint

- Preserved the in-progress exporter identity/emptiness/generation safety work, route idempotency fix,
  and real database regression-test conversion before continuing evaluator-directed repairs.

- `backend/src/mtg_helper/models/new_cards.py`: replaced AI assessment response fields with transparent source-tag match models.
- `backend/src/mtg_helper/services/new_cards/repository.py`: implemented owner-scoped, read-only current-generation Commander tag matching and source-status checks.
- `backend/src/mtg_helper/services/new_cards/service.py` and router: retained explicit local plan/dismiss/undo actions without model or worker execution.
- `backend/src/mtg_helper/main.py`, config, admin router, and obsolete evaluator/worker tests: removed New Cards analysis worker, controls, and runtime AI dependency while retaining historical tables.
- `backend/scripts/copy_new_cards_local.py`: added source-read-only, owner-filtered local export with loopback/equivalent-target and nonempty-target guards.
- `frontend/components/new-cards-panel.tsx`, state, types, and admin panel: display source tag explanations/status and remove generated advice/analysis controls.
- `GLOSSARY.md` and `VERIFY.md`: document tag-match terms and safe dedicated-local run procedure.
- Focused tests: added source-unavailable and copy-target safety seams; replaced obsolete AI New Cards checks.

## Verification

Green:

```text
backend: uv run pytest -q -W error tests/test_new_cards_tag_matches.py tests/test_copy_new_cards_local.py
3 passed in 9.89s
backend: uv run pytest -q -W error -m no_db tests/test_copy_new_cards_local.py
2 passed in 0.02s
backend: uv run ruff check .; uv run ruff format --check .; uv run ty check src/
All checks passed
frontend: vitest selected, tsc, oxlint, oxfmt
3 tests passed; Found 0 warnings and 0 errors; all matched files use correct format
```

The full backend suite was attempted twice. It reaches the pre-existing unrelated
`tests/test_buylist.py::test_buylist_reports_partial_owned_deficit` failure (`'' != '3 Sol Ring'`)
and did not complete within the available execution window. It was not changed because the approved
scope explicitly excludes unrelated failing-test repair. The isolated PostgreSQL tag-match test ran
successfully after starting the disposable local PostgreSQL service. No production export or local
interactive smoke was run; those require the configured approved account and dedicated local target.

No intentional deviation from the approved feature scope.

## Round 2

- `backend/src/mtg_helper/services/new_cards/service.py`: returns success for a repeated plan
  request before recomputing the now-hidden tag match, preserving API idempotency.
- `backend/scripts/copy_new_cards_local.py`: rejects routed or nonempty targets, verifies matching
  source generations before copying, and copies only plan-linked approved-owner collection records
  needed for local plan reference integrity.
- `backend/tests/test_new_cards_tag_matches.py`: adds authenticated real-SQL route coverage for
  read-only blocked-transport GETs, hierarchy/ranking, ownership/local dismissals, idempotent plans,
  current source statuses, and completion legality/color/copy guards.
- `backend/tests/test_copy_new_cards_local.py`: replaces validator-only checks with real source/target
  database export tests covering owner filtering, read-only source preservation, linked plans, target
  emptiness, DSN identity, and generation mismatch refusal.
- `frontend/components/new-cards-panel.test.tsx` and `frontend/components/admin-panel.test.tsx`:
  render the real panels with synthetic session/HTTP state to verify tag provenance, empty/error
  distinction, retained Scryfall sync, and absent New Cards analysis controls.
- `GLOSSARY.md`, `frontend/components/admin-panel.tsx`, and `frontend/lib/types.ts`: repair unrelated
  round-1 UTF-8 mojibake without changing their intended behavior.

### Verification

```text
backend (isolated tagmatch_build2_test):
uv run ruff check .
All checks passed!
uv run ruff format --check .
226 files already formatted
uv run ty check src/
All checks passed!
uv run pytest -q -W error tests/test_new_cards_tag_matches.py tests/test_copy_new_cards_local.py
14 passed in 11.87s

frontend:
node node_modules/vitest/vitest.mjs run components/new-cards-panel.test.tsx components/admin-panel.test.tsx
Test Files 2 passed (2); Tests 3 passed (3)
node node_modules/typescript/bin/tsc --noEmit
passed
oxlint app lib components
Found 0 warnings and 0 errors.
oxfmt --check .
All matched files use the correct format.
```

No production DSN, account export, app login, or running-app smoke was accessed in this round. The
parent retains the separately authorized export and local authenticated smoke after these safety checks.

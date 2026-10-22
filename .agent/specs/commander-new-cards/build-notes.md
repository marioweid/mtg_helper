# Build notes — round 2

- `backend/src/mtg_helper/services/feature_flag_service.py`: removes New Cards automation from
  generic admin flags and rejects account-scoped automation access at the service boundary.
- `backend/src/mtg_helper/services/new_cards/repository.py`: reports a complete current
  Commander-Konstellation as `idle` and splits the status read model below the complexity limit.
- `backend/src/mtg_helper/services/new_cards/service.py`: records completed constellations and
  reports separate waiting, finished, and failed global-control counts.
- `backend/src/mtg_helper/sql/schema.sql`: persists completion timestamps and removes obsolete
  account-specific New Cards automation rows on schema application.
- `backend/tests/test_new_cards_automation.py`: makes the concurrent-claim check deterministic and
  covers completed status and generic/account automation bypass prevention.
- `frontend/components/admin-new-cards-panel.tsx`: shows finished work separately and refreshes the
  read-only control status every three seconds.
- `frontend/components/admin-new-cards-panel.test.tsx`: covers the honest finished status display.
- `frontend/components/new-cards-panel.tsx`: describes a completed, deck-locally dismissed result
  as no further visible cards rather than pending work.
- `frontend/components/new-cards-panel.test.tsx`: covers the all-dismissed completed display.

## Verification

```text
backend: TEST_DATABASE_URL=postgresql://mtg@127.0.0.1:55441/mtg_helper_test
         uv run pytest -q -W error tests/test_new_cards_automation.py
         15 passed in 13.93s
backend: selected AC06/AC11/AC13/AC14 regression, ruff check/format, ty check
         4 passed, 11 deselected; all static checks passed
backend: ruff check --ignore-noqa --select C901 new_cards/repository.py
         All checks passed
frontend: vitest New Cards components
          38 passed
frontend: full vitest / tsc / oxlint / oxfmt / next build
          116 passed; no type, lint, or format errors; build succeeded
```

The isolated PostgreSQL 16 cluster was started on loopback port 55441 and stopped after testing.
The full backend suite completed with 1309 passed and 9 failures in unrelated buylist, keyword,
planned-change, and tag-service tests. They are outside this round's requested FAIL/VIOLATES scope;
no changes were made to them.

## Deviations

No product-scope deviation. The existing untracked `GLOSSARY.md` was preserved. The full backend
suite is not green because of the nine out-of-scope failures listed above; the targeted acceptance
suite and all required static/frontend checks are green.

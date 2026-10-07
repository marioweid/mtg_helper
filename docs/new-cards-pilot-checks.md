# Experimental New Cards pilot — verification

## Now

Implementation is on `feat/new-cards-pilot`. Independent read-only review passed with no blockers;
PR publication is the remaining handoff step.
No production deployment, production database write, or additional paid model call was performed.
The existing research budgets remain exhausted. See [contract](new-cards-pilot-contract.md) and
[operating instructions](../OPERATIONS.md#experimental-new-cards-pilot).

## Local evidence (2026-10-07)

- PostgreSQL 16.8 on isolated localhost port 15439, disposable `mtg_helper_test` database.
- **227 backend tests passed with warnings treated as errors**, including all research regressions,
  discovery/evidence gates, real SQL/API pilot tests, Scryfall parsing, identity, deck CRUD and
  assistant physical-context tests. No real model transport was used.
- **31 frontend tests passed** (30 New Cards, one planned-change panel). The pilot tests exercise
  production state/controller/request code with a hook-scheduling adapter; they are not a real
  browser end-to-end test.
- Full backend Ruff and `ty check src/` passed. Scoped Ruff format, frontend TypeScript,
  zero-warning oxlint and oxfmt passed. New production functions meet the 100-line, five-positional
  parameter and complexity-eight bounds.
- Compose configuration and the daily/weekly scheduler's shell syntax validated without resolving
  or printing credentials. Docker daemon/browser/deployed-stack smoke tests were not performed.
- Source validation replayed the ignored, frozen 2026-10-04 Scryfall archives: all **38,705** Oracle
  fact records validated; **472** released/legal designs met conservative pilot discovery filters
  as of October 7. This is not a per-deck ranking or recall measurement, and used no new download.
- In-memory mutations disabling quotation verification and increasing the daily quota were both
  caught by their tests. Source files were unchanged. Frontend sequence-guard mutation was also
  caught during UI implementation.
- API/SQL tests cover all five owner boundaries, read-without-work, eight-card batches, rejected
  coverage, source/candidate/deck/notes/preferences/pending-plan invalidation, partner color union,
  dismiss/undo, explicit idempotent planning, source publication locks, account-wide leases,
  stale worker rejection, quota reset, failed-provider cache retention, input bounds, missing
  catalogs, exact expiry/future filtering, and additive schema replay.
- Both completion routes reject banned/off-color/duplicate/withdrawn/now-commander additions and
  roll back the entire revision. Saved plans survive age expiry; canonical repair preserves pilot
  provenance. Source withdrawal does not delete cards or plans.

## Independent review

One read-only review covered the application diff from `8e96de91`, including ownership, cache/lease
races, source publication, schema replay, completion guards and frontend integration. No blockers
were found. The reviewer inspected tests/check reports but did not independently rerun them, and did
not evaluate frozen research or claim real-browser/provider verification.

## Existing test failures, reproduced on the base backend

The broader affected run found **six failures and eight passes** in
`backend/tests/test_planned_changes.py`. All six reproduce using the unchanged backend from
`8e96de91` in the separate UI worktree. These tests request multiple Sol Rings, while existing
identity normalization enforces singleton limits. They were not weakened or silently skipped:

- `test_planned_addition_is_excluded_from_physical_deck`
- `test_opposite_plan_offsets_existing_quantity`
- `test_partial_addition_completion_leaves_remainder`
- `test_selected_collection_is_revalidated_atomically`
- `test_immediate_add_consumes_matching_plan`
- `test_shopping_list_uses_only_selected_collections`

Adjacent pre-existing dead code: `planned_change_service.complete_plan` has no callers; actual
single and batch endpoints use `revision_service.apply_revision`. The pilot guards the real path.
Removing that legacy function is separate cleanup, not part of this feature.

## Reproduce focused checks

Use a disposable PostgreSQL database owned by role `mtg`; the fixture drops/recreates its public
schema. Never set `TEST_DATABASE_URL` to a development or production database containing user data.

```bash
cd backend
uv run ruff check .
uv run ty check src/
TEST_DATABASE_URL=postgresql://mtg@127.0.0.1:15439/mtg_helper_test uv run pytest -q -W error \
  tests/test_new_cards*.py tests/test_scryfall_pipeline.py tests/test_card_identity_service.py \
  tests/test_deck_crud.py tests/test_assistant_deck_context.py

cd ../frontend
node node_modules/vitest/vitest.mjs run \
  components/new-cards-panel.test.tsx components/planned-changes-panel.test.tsx
node node_modules/typescript/bin/tsc --noEmit
```

Mechanical tests cannot establish MTG semantic correctness. Both research evaluators retained
rules mistakes; the pilot remains explicitly unverified, with no automatic deck changes. Real
browser/deployed-source/provider smoke testing remains an operator acceptance step after review;
it is not implied by unit/integration tests or by opening the PR.

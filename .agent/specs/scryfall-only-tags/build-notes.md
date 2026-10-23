# Build notes — scryfall-only-tags round 2

## Changed

- `OPERATIONS.md`: updates active refresh guidance to the atomic Scryfall-only source publication.
- `docs/new-cards-pilot-contract.md`: documents the production-default New Cards worker accurately.
- `docs/scryfall-label-cutover-runbook.md`: adds backup, rehearsal, approval, Apply, and postcheck sequence.
- `backend/scripts/dev_setup_db.py`: retires legacy label sync phases from local setup.
- `backend/scripts/migrate_scryfall_labels.py`: makes source generation reads transactional, preserves already-converted UUIDs, restricts targets, and creates new private reports safely.
- `backend/scripts/tag_focused_cards.py`: removes the retired rule-label writer script.
- `backend/src/mtg_helper/config.py`: removes retired MTGJSON and community-label writer settings.
- `backend/src/mtg_helper/models/decks.py`: exposes Oracle tags while excluding legacy label arrays from deck responses.
- `backend/src/mtg_helper/routers/admin.py`: removes manual legacy label membership and theme routes.
- `backend/src/mtg_helper/services/admin_jobs.py`: keeps only Scryfall source-publication job slots.
- `backend/src/mtg_helper/services/archidekt_commander_recs_service.py`: removes a retired tag-writer setting dependency.
- `backend/src/mtg_helper/services/{mtgjson,tag_service,moxfield_hub_service,archidekt_tag_service}.py`: removes retired runtime label writers.
- `backend/src/mtg_helper/services/deck_service.py`: projects direct Oracle tags in deck and commander views.
- `backend/src/mtg_helper/services/keyword_catalog_service.py`: validates model choices against Scryfall UUIDs and exact printed keywords.
- `backend/src/mtg_helper/sql/schema.sql`: recreates the deck detail view with direct Oracle-tag projection after source tables exist.
- `backend/tests/test_admin_jobs.py`: replaces obsolete job and refresh contracts with Scryfall-only behavior.
- `backend/tests/test_scryfall_label_cutover.py`: adds fixed AC04 and AC06–AC11 regressions.
- `backend/tests/{test_mtgjson_pipeline,test_tag_service,test_theme_sources}.py`: removes obsolete writer tests.
- `frontend/app/decks/new/{page,agent/page}.tsx`: removes active Moxfield hub label instructions.
- `frontend/components/{theme-manager,theme-manager.test}.tsx`: removes unreachable legacy theme-management UI.
- `frontend/components/{admin-panel,scryfall-tag-picker}.test.tsx`: supplies the requested rendered source-label/admin checks.

## Verification

- `backend/`: `uv run pytest -q -W error -m no_db` — `538 passed, 687 deselected`.
- `backend/`: `uv run pytest -q -W error tests/test_scryfall_label_cutover.py -k 'ac06 or ac07 or ac08 or ac09 or ac11'` — `5 passed, 4 deselected`.
- `backend/`: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check src/` — all passed.
- `frontend/`: Vitest — `24 passed, 116 passed`; TypeScript, oxlint, oxfmt, and production build all passed.
- `backend/`: full `uv run pytest -q -W error` is blocked, not green: every database-backed test setup fails before test execution with `ConnectionRefusedError [WinError 1225]` for the disposable local `_test` PostgreSQL database. Docker Desktop is unavailable; no live target was used.

## Deviations and blockers

- The required populated-schema migration rehearsal and database-backed AC04/AC05/AC08/AC09 routes remain unverified because no disposable PostgreSQL is available.
- Legacy-column DDL is deliberately not executed by the migration until its remaining consumers are jointly converted; no destructive cutover was attempted without the required rehearsal.
- No production migration, source refresh, external-resource deletion, paid model call, or authenticated browser smoke was performed.

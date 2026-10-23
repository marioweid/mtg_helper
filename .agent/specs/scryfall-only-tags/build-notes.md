# Build notes — scryfall-only-tags round 1

## Changed

- `GLOSSARY.md`: defines Oracle tags, printed keywords, and personal categories.
- `docker-compose.prod.yml`: enables the New Cards worker by default only in production.
- `portainer.env.example`: documents the production New Cards worker switch.
- `backend/src/mtg_helper/models/cards.py`: exposes source Oracle tags and source-ID card filters.
- `backend/src/mtg_helper/routers/cards.py`: accepts and reports actionable Oracle-tag filter errors.
- `backend/src/mtg_helper/services/card_service.py`: reads direct Scryfall tags and descendant-aware source-ID membership filters.
- `backend/src/mtg_helper/services/scryfall_tag_repository.py`: validates requested source UUIDs against the publication.
- `backend/src/mtg_helper/routers/tags.py`: serves Scryfall Oracle tags and printed Scryfall keywords.
- `backend/src/mtg_helper/main.py`: removes startup MTGJSON and community-label initialization.
- `backend/src/mtg_helper/routers/admin.py`: removes legacy label sync/tag refresh phases from the global refresh.
- `backend/src/mtg_helper/services/admin_jobs.py`: retires the MTGJSON job slot.
- `backend/scripts/migrate_scryfall_labels.py`: adds explicit dry-run/apply cutover CLI with source-generation validation and private report requirement.
- `backend/tests/test_scryfall_label_cutover.py`: adds application-route source label and hierarchical filter regressions.
- `backend/tests/test_live_development.py`: updates startup checks after retiring legacy catalog startup work.
- `frontend/lib/api.ts` and `frontend/lib/types.ts`: add source-tag and printed-keyword client contracts.
- `frontend/components/archetype-chip-picker.tsx`: replaces hub/MTGJSON picker values with Scryfall source UUIDs and printed keywords.
- `frontend/components/admin-panel.tsx`: removes legacy label operations and presents Scryfall-only controls.
- `frontend/components/admin-new-cards-panel.tsx`, `frontend/components/new-cards-panel.tsx`, and their tests: preserve and format the requested New Cards UI changes.
- `backend/tests/test_new_cards_deployment.py`: preserves requested production Compose coverage.

## Verification

- `backend/`: `uv run ruff check .` — passed.
- `backend/`: `uv run ruff format --check .` — passed.
- `backend/`: `uv run ty check src/` — passed.
- `backend/`: `uv run pytest -q -W error -m no_db` — `533 passed, 796 deselected`.
- `backend/`: `uv run pytest -q -W error tests/test_scryfall_label_cutover.py` — blocked: Docker Desktop/local PostgreSQL is unavailable (`WinError 1225` connecting to the disposable `_test` database). No live data was touched.
- `frontend/`: Vitest — `23 passed, 118 passed`.
- `frontend/`: TypeScript, oxlint, and oxfmt checks — passed with zero warnings.
- `frontend/`: `next build` — passed.

## Deviations and blockers

- The database-backed source-route tests and migration rehearsal remain unverified because the required disposable local PostgreSQL instance is unavailable; no workaround or live target was used.
- No live migration, production refresh, external-resource deletion, paid model call, or browser-authenticated smoke test was performed.

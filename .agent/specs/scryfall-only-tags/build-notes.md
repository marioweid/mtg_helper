# Build notes — scryfall-only-tags round 3

## Changed

- `backend/scripts/migrate_scryfall_labels.py`: validates canonical local DB identity and drops retired label DDL during Apply.
- `backend/src/mtg_helper/models/ai.py`: removes retired trait/token and qualifying-stage response fields.
- `backend/src/mtg_helper/models/decks.py`: projects Oracle tags and exact keywords without derived role fields.
- `backend/src/mtg_helper/routers/ai.py`: rejects invalid source selections at the route boundary.
- `backend/src/mtg_helper/routers/decks.py`: reports invalid persisted Oracle-tag selections and removes auto-role wording.
- `backend/src/mtg_helper/services/agents/commander_suggestor_agent.py`: prompts for source UUIDs and exact printed keywords only.
- `backend/src/mtg_helper/services/agents/deck_doctor_agent.py`: uses direct Oracle-tag membership and personal categories.
- `backend/src/mtg_helper/services/agents/describe_agent.py`: removes retired label catalog prompt material.
- `backend/src/mtg_helper/services/agents/extract_agent.py`: emits source identities without legacy fallback labels.
- `backend/src/mtg_helper/services/ai_service.py`: retrieves by source identities and assigns only the requested build category.
- `backend/src/mtg_helper/services/assistant_deck_context.py`: supplies source cards facts without retired tag data.
- `backend/src/mtg_helper/services/builder_roles.py`: deleted retired role-classifier module.
- `backend/src/mtg_helper/services/card_search_tool.py`: validates exact source UUID filters.
- `backend/src/mtg_helper/services/commander_coach/pipeline.py`: uses personal categories and direct Oracle memberships, not classifiers.
- `backend/src/mtg_helper/services/commander_coach/synergy_scoring.py`: removes retired label evidence.
- `backend/src/mtg_helper/services/commander_suggestor_service.py`: scores source UUIDs and exact keywords without traits/tokens.
- `backend/src/mtg_helper/services/deck_fit_service.py`: compares selected Oracle memberships and personal categories only.
- `backend/src/mtg_helper/services/deck_optimizer_service.py`: stops consuming derived qualifying stages.
- `backend/src/mtg_helper/services/deck_service.py`: validates, persists, and projects source-tag selections.
- `backend/src/mtg_helper/services/import_service.py`: removes legacy global-label reads from imported cards.
- `backend/src/mtg_helper/services/keyword_catalog_service.py`: validates source UUIDs and exact printed keywords.
- `backend/src/mtg_helper/services/mana_base_service.py`: uses card facts and no tag-derived ramp/draw counts.
- `backend/src/mtg_helper/services/mtg_assistant_tools.py`: removes retired assistant tag transport.
- `backend/src/mtg_helper/services/mtg_card_search.py`: filters source memberships and rejects invalid source filters.
- `backend/src/mtg_helper/services/onboarding_service.py`: counts explicit personal categories only.
- `backend/src/mtg_helper/services/playtest_service.py`: derives mana/draw simulation facts from card text, never legacy labels.
- `backend/src/mtg_helper/services/retrieval_service.py`: removes Moxfield/theme inclusion and legacy-label retrieval; uses Scryfall memberships.
- `backend/src/mtg_helper/services/swap_service.py`: carries source-only suggestion fields.
- `backend/src/mtg_helper/services/theme_service.py`: deleted retired community-label catalog.
- `backend/src/mtg_helper/services/theme_suggestion_service.py`: deleted retired community-label suggestions.
- `backend/src/mtg_helper/sql/migrate_002_collapse_interaction.sql`: deleted retired interaction-label migration.
- `backend/src/mtg_helper/sql/schema.sql`: removes retired label storage and projects Oracle tags in the deck view.
- `backend/tests/conftest.py`: seeds Scryfall source fixtures without legacy card labels.
- `backend/tests/test_agent_run_contracts.py`: checks source-only agent contracts.
- `backend/tests/test_ai_service.py`: updates retrieval fixtures to source-only fields.
- `backend/tests/test_builder_roles.py`: deleted tests for retired role classifier.
- `backend/tests/test_collection_filter.py`: seeds direct Oracle memberships.
- `backend/tests/test_collection_resolution.py`: seeds direct Oracle memberships.
- `backend/tests/test_commander_coach_pipeline.py`: verifies invalid natural-language source tags are rejected.
- `backend/tests/test_commander_suggestor_service.py`: tests source UUID and exact keyword behavior.
- `backend/tests/test_deck_fit_service.py`: tests direct Oracle membership and personal-category behavior.
- `backend/tests/test_describe.py`: updates source-only prompt assertions.
- `backend/tests/test_mtg_assistant_tools.py`: removes retired assistant transport expectations.
- `backend/tests/test_mtg_card_search.py`: tests direct membership source search.
- `backend/tests/test_playtest_service.py`: replaces legacy role-label fixtures with Scryfall card-fact cases.
- `backend/tests/test_price_filter.py`: seeds direct Oracle memberships.
- `backend/tests/test_scryfall_label_cutover.py`: adds source-cutover API, migration, and selection checks.
- `backend/tests/test_theme_suggestion_service.py`: deleted tests for retired theme suggestions.
- `frontend/app/decks/[id]/build/page.tsx`: counts personal categories without auto-derived roles.
- `frontend/app/decks/[id]/keywords/page.tsx`: labels deck selection as Scryfall source tags.
- `frontend/app/decks/new/keywords/page.tsx`: labels new-deck selection as Scryfall source tags.
- `frontend/app/decks/new/suggest/page.tsx`: removes trait/token intent fields.
- `frontend/components/archetype-chip-picker.tsx`: uses source UUID selections.
- `frontend/components/card-detail-panel.tsx`: removes auto-role display and keeps personal category controls.
- `frontend/components/card-workspace.test.tsx`: removes retired deck-card fixture fields.
- `frontend/components/coach-deck-workspace.tsx`: counts personal categories only.
- `frontend/components/deck-scorecard.tsx`: counts personal categories only.
- `frontend/components/personalization-removal.test.tsx`: removes retired suggestion fixture field.
- `frontend/lib/types.ts`: removes retired label, trait, token, and qualifying-stage client contracts.

## Verification

- `backend/`: isolated DB targeted source/consumer suite with transports disabled — `190 passed in 58.89s`.
- `backend/`: `uv run ruff check .` — `All checks passed!`.
- `backend/`: `uv run ruff format --check .` — `223 files already formatted`.
- `backend/`: `uv run ty check src/` — `All checks passed!`.
- `frontend/`: `node node_modules/typescript/bin/tsc --noEmit` — passed.
- `frontend/`: scoped Vitest card/source UI checks — `4 passed`, `7 passed` tests.
- `backend/`: migration CLI dry-run against isolated `scryfall_build3_test` — failed safely with `Scryfall card/tag generation is absent or mismatched; refusing cutover`; Apply was not attempted.

## Deviations and residual issues

- No production migration, source refresh, external transport, paid model call, deployment, or PostgreSQL shutdown was performed.
- The final isolated database no longer had a matching Scryfall card/tag generation after the focused test session, so this round did not produce a fresh successful CLI Apply rehearsal. The fail-fast dry-run behavior is the actual outcome; the earlier private-report rehearsal is not claimed as final verification.
- No full backend or frontend gate was rerun in this final snapshot; independent evaluation must assess the remaining acceptance coverage and full-suite regressions.

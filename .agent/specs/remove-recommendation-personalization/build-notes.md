# Build notes — round 1

## Changed

- `backend/src/mtg_helper/main.py`: removed retired deck-feedback router registration.
- `backend/src/mtg_helper/models/ai.py`: removed persistent-memory request/response contracts.
- `backend/src/mtg_helper/models/{feedback,preferences,ranking_weights}.py`: deleted retired contracts.
- `backend/src/mtg_helper/routers/ai.py`: removed memory routes and Doctor memory loading.
- `backend/src/mtg_helper/routers/me.py`: removed preference and ranking-weight routes.
- `backend/src/mtg_helper/routers/feedback.py`: deleted retired feedback routes.
- `backend/src/mtg_helper/services/{assistant_service,mtg_assistant}.py`: retained current-chat turns and removed memory injection/routing.
- `backend/src/mtg_helper/services/{coach_memory,feedback,preference,profile,ranking_weight}_service.py`: deleted retired implementations.
- `backend/src/mtg_helper/services/ai_service.py`: removed account-taste ranking, avoid exclusion, and feedback weighting.
- `backend/src/mtg_helper/services/retrieval_service.py`: retained fixed source-evidence ranking without personal inputs or tunable weights.
- `backend/src/mtg_helper/services/{deck_service,deck_fit_service}.py`: removed pet-card protection.
- `backend/src/mtg_helper/services/new_cards/{repository,evaluator,service}.py`: removed stored-taste context, filtering, and cache dependence.
- `backend/src/mtg_helper/services/recommendations/{repository,pipeline}.py`: retained physical/planned exclusions and removed avoid-card exclusion.
- `backend/src/mtg_helper/services/agents/deck_doctor_agent.py`: removed persistent-memory prompt behavior.
- `backend/src/mtg_helper/services/commander_coach/{__init__,orchestrator,pipeline,signal_lanes,validators}.py`: removed memory behavior and redundant coach wrapper.
- `backend/scripts/{eval_coach_suggestions,live_assistant_check}.py`: call the unified Assistant entry point.
- `backend/tests/conftest.py`: removed the obsolete profile-service cache reset.
- `backend/tests/test_{coach_memory,coach_memory_routing,feedback,preferences,profile_service}.py`: deleted retired feature-only coverage.
- `backend/tests/test_{assistant_sessions,commander_coach_pipeline,retrieval_service,ai_service,new_cards_pilot}.py`: replaced old personalization expectations with retained behavior.
- `backend/tests/test_{assistant_personalization_removal,recommendation_personalization_removal,new_cards_personalization_removal,personalization_data_retention,retired_personalization_api}.py`: added removal/data-retention coverage.
- `frontend/app/preferences/page.tsx`: replaced settings with the required empty state.
- `frontend/app/decks/[id]/{page,build/page,coach/page}.tsx`: removed pet-card requests/badges, persisted rejects, and memory editor/fetches.
- `frontend/components/{card-suggestion,deck-browser-panel,deck-category-group,deck-compact-columns,expandable-deck-bar}.tsx`: removed pet-card props and badges.
- `frontend/components/{preference-form,preference-list}.tsx`: deleted retired settings controls.
- `frontend/lib/{api,types}.ts`: removed retired client methods and contracts.
- `frontend/app/preferences/page.test.tsx`: covers the static Preferences state.
- `frontend/app/decks/coach-personalization.test.tsx`: covers absent memory client methods.

## Verification

- `backend/`: `uv run ruff check .` → all checks passed.
- `backend/`: `uv run ruff format --check .` → 239 files already formatted.
- `backend/`: `uv run ty check src/` → all checks passed.
- `backend/`: `uv run pytest -q -W error -m no_db` → 518 passed, 794 deselected.
- `frontend/`: `corepack pnpm lint` → 0 warnings and 0 errors.
- `frontend/`: `corepack pnpm typecheck` → passed.
- `frontend/`: `corepack pnpm test` → 21 files, 106 tests passed.
- `frontend/`: `corepack pnpm build` → production build passed.
- Mutation proof: temporarily restoring `apiClient.getCoachMemory` made
  `app/decks/coach-personalization.test.tsx` fail; the mutation was reverted.
- Full backend `uv run pytest -q -W error` is blocked because Docker Desktop is unavailable and
  the required isolated PostgreSQL `_test` database cannot be started (`docker_engine` pipe missing).
  The run consequently reported connection-refused setup errors; no live database was contacted.

## Deviations

- Database and browser/manual checks are blocked by the unavailable local Docker daemon. No database
  mode, DSN, environment file, or shared/live data was changed.

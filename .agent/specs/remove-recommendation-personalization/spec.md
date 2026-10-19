# Remove recommendation personalization and persistent assistant memory

**Size:** L

## Intent

Recommendations use source evidence and explicit deck context, not saved account tastes,
feedback boosts, or user-adjustable ranking factors. The Assistant keeps conversational
follow-ups but no longer remembers instructions across chats. Preferences remains in the
navigation as an empty page. This project has no Jira ticket for this change.

## Non-goals

- Redesigning source ranking, replacing recommendation engines, or cutting other features.
- Removing account identity, display names, authentication, ownership, decks, or collections.
- Removing current-chat history, conversation IDs, tracing, or streaming progress.
- Removing deck descriptions, goals, themes, bracket, role targets, price/type/collection filters.
- Removing Builder session-local rejection, New Cards dismissal/undo, or Discover quality reports.
- Deleting historical preference, weight, feedback, memory, assessment, run, or trace data.
- Committing, pushing, or discarding unrelated work, including live-database development changes.

## Acceptance

Read the current `VERIFY.md` before booting or testing. Use its isolated database procedure;
never reset shared/live data or enable live-mode startup maintenance. Preserve existing env files.
The commands below use pytest to exercise a running in-process FastAPI app and frontend tests
to render actual pages/modules. No live model calls are required. Backend commands run from
`backend/`; frontend commands from `frontend/`. Named new test files are implementation deliverables.
Database tests require PostgreSQL 16 and the disposable local `_test` database from `VERIFY.md`.
Run them with the isolated backend container procedure there, substituting the relevant test files
for its example selection. Do not override its fixed `TEST_DATABASE_URL` to shared/live data.
Use `-m no_db` for offline pytest checks; that does not verify database criteria.
For manual UI checks, follow `VERIFY.md` without changing the active database mode implicitly;
use isolated mode for any edits. Shared/live UI checks must be read-only.

1. **AC1** [ui] The Assistant loads and answers without a saved-memory editor or request.
   verify: `pnpm test -- app/decks/coach-personalization.test.tsx` → passing checks that the
   Assistant loads the deck without calling memory endpoints, shows no Edit/Save memory control,
   and displays a normal answer. Manually open a deck's Assistant and confirm the same behavior
   on the isolated local stack with a deterministic provider adapter.

2. **AC2** [api] Assistant turns preserve follow-up context and progress without reading,
   injecting, or changing saved memory or handling remember/forget commands specially.
   verify: `uv run pytest -q -W error tests/test_assistant_personalization_removal.py
   tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py` → passing checks
   using a deterministic model adapter that captures prompt/history; saved notes are absent,
   explicit current-chat instructions/history remain, and sync/background turns preserve tracing,
   failure handling, account context, grounded output, and assistant progress events. Include
   the separate doctor path and ensure it also does not load or inject saved memory.

3. **AC3** [api] Retired memory endpoints and response contracts are absent.
   verify: `uv run pytest -q -W error tests/test_retired_personalization_api.py -k memory` →
   authenticated GET/PUT requests to a valid deck's `/api/v1/decks/{id}/coach/memory` return
   404; OpenAPI no longer exposes those routes or memory-only models/fields/modes; actual
   Assistant responses contain no `coach_memory` or `memory_updated` fields.

4. **AC4** [ui] Preferences remains accessible but has no settings or retired network calls.
   verify: `pnpm test -- app/preferences/page.test.tsx` → passing checks for the Preferences
   navigation link and page heading, exact text `Nothing in here yet.` and
   `Profile settings may come in the future.`, no settings/forms/weights/mix/toggles, and no
   preference or ranking-weight requests. Manually visit `http://localhost:3000/preferences`
   and confirm the empty state and retained navigation link.

5. **AC5** [api] Retired account-preference, ranking-weight, and legacy feedback routes are absent.
   verify: `uv run pytest -q -W error tests/test_retired_personalization_api.py` → authenticated
   POST/GET `/api/v1/me/preferences`, DELETE `/api/v1/me/preferences/{id}`, GET/PUT
   `/api/v1/me/ranking-weights`, POST/GET `/api/v1/decks/{id}/feedback`, and DELETE
   `/api/v1/decks/{id}/feedback/{feedback_id}` return 404; OpenAPI omits retired routes/models;
   account GET/PATCH and collection access still work. Valid fixture IDs are used throughout.

6. **AC6** [api] Recommendation and deck-fit results no longer depend on saved account tastes.
   verify: `uv run pytest -q -W error tests/test_recommendation_personalization_removal.py` →
   seed pet/avoid cards, avoided archetypes, general notes, boosting flags, extreme weights,
   trusted quota, legacy up/down/reject feedback, and cross-deck taste history; compared with
   the same deck/source state without those settings, Builder/free-form/mana/swap retrieval
   have identical ordered card identities, deck fit has no pet-card protection, and New Cards
   and Discover do not exclude or favor cards because of those records. Explicit deck
   constraints, source inclusion signals, canonical identity, and structural protection remain.

7. **AC7** [api] New Cards assessments ignore saved memory/preferences and invalidate advice
   generated using the old personalized context without deleting its historical records.
   verify: `uv run pytest -q -W error tests/test_new_cards_personalization_removal.py` → prompt
   context excludes saved notes/preferences, changing old rows does not change new context
   fingerprints/results, an assessment cached with the old context is not reused as current,
   and the historical assessment row is retained. Use a captured deterministic provider response.

8. **AC8** [ui] Deck workflows retain explicit actions without collecting personal feedback.
   verify: run `pnpm test --` with `components/personalization-removal.test.tsx`,
   `components/card-workspace.test.tsx`, `components/discover-state.test.ts`,
   `components/new-cards-panel.test.tsx`, and `lib/coach-conversation.test.ts` → passing checks
   that there are no pet-card hearts or preference requests in deck/Builder views; Builder
   Reject replaces and excludes locally without calling the retired feedback endpoint;
   navigation starts a fresh rejection session; New Cards dismiss/undo and Discover Report
   incorrect still work; planned additions, filters and bounded conversation history remain.

9. **AC9** [db] Applying the updated schema preserves stored personalization and unrelated data.
   verify: `uv run pytest -q -W error tests/test_personalization_data_retention.py` against only
   the disposable local test database → seed/snapshot rows in `preferences`,
   `account_ranking_weights`, `deck_feedback`, and `deck_coach_memory`, plus
   accounts/decks/collections; apply schema twice; snapshots remain unchanged. Repeated new
   application requests do not read, update, or insert legacy settings. Test-fixture resets
   and existing explicit account/deck deletion behavior are not feature retirement.

## Modules

- `assistant_service.py`: run one authorized traced turn · hides turn/session lifecycle;
  memory routing disappears · deep · existing.
- `mtg_assistant.py`: run assistant with current deck/history · hides bounded model execution,
  deterministic tools, and grounding; saved-memory fields disappear · deep · existing.
- `agents/deck_doctor_agent.py`, `commander_coach/pipeline.py`, and
  `commander_coach/validators.py`: existing analysis interfaces · hide retained analysis and
  validation; remove memory-specific behavior only · deep · existing.
- `routers/ai.py`, `models/ai.py`: HTTP/request/response interfaces · transport/contracts only;
  remove memory routes/models/modes · shallow · existing.
- `preference_service.py`, `ranking_weight_service.py`, `profile_service.py`,
  `feedback_service.py` and their dedicated models/router: retired personalization interfaces
  · no retained application implementation; delete callers and definitions · existing, removed.
- `routers/me.py`, `main.py`: account and routing interfaces · retain account/collection
  operations and remove retired route registrations · shallow · existing.
- `ai_service.py`, `retrieval_service.py`: recommendation/retrieval interfaces · hide fixed
  source ranking and explicit deck constraints, with no account-taste inputs · deep · existing.
- `deck_service.py`, `deck_fit_service.py`: deck detail/fit interfaces · retain ownership,
  collection enrichment and structural protections; remove pet-card protection · deep · existing.
- `new_cards/repository.py`, `evaluator.py`, `service.py`: assessment interfaces · hide source
  candidates, context fingerprints, and assessment validity without saved tastes · deep · existing.
- `recommendations/repository.py` and existing reporting modules: exclusions/report interfaces
  · hide physical/planned exclusions and run quality reports, not account avoids · deep · existing.
- `frontend/app/preferences/page.tsx`, `components/nav.tsx`: Preferences entry interface ·
  retain navigation and static empty state; delete exclusive settings modules · shallow · existing.
- `frontend/app/decks/[id]/coach/page.tsx`: Assistant UI interface · hides active conversation
  and streaming, without persistent-memory state/editor/fetches · deep · existing.
- Deck/Builder pages and card/workspace modules: existing browsing/action interfaces ·
  preserve deck workflows; delete pet-card props and persisted rejection writes · existing.
- `frontend/lib/api.ts`, `types.ts`, and progress handling: typed client interfaces · remove
  retired endpoints/contracts/events while retaining account and chat contracts · shallow · existing.
- `sql/schema.sql`: idempotent schema interface · retains legacy tables as inactive stored
  data, without destructive retirement migrations · deep · existing.
- Existing evaluation scripts, fixtures, tests and current operational docs: CLI/check
  interfaces · remove obsolete memory/preference assumptions and verify retained behavior · existing.

## Test seams

- Existing FastAPI HTTP seam with real disposable PostgreSQL: catches route retirement,
  ownership, data retention, hidden personalization reads, and public result differences;
  misses browser presentation and real external-provider behavior.
- Existing assistant/provider seam with deterministic model adapter: catches prompt/context,
  current-chat history, memory-command removal, grounding, progress and failures; misses
  live-model response quality and external availability. Keep real orchestration under test.
- Existing frontend page/action seam with a test HTTP adapter: catches empty-state copy,
  retired requests, badges, local rejection and retained actions; misses production OAuth
  and deployment networking. Use browser verification for the actual navigation/pages too.

## Constraints

- Delete retired implementations, imports, client methods, contracts and exclusive controls;
  do not replace them with no-op services, compatibility shims, flags or hidden settings.
- Preserve old table definitions and idempotent schema maintenance needed to retain data.
  Application recommendation/assistant paths must neither read nor write those old tables.
- Account profiles are identity data; inferred recommendation taste profiles are removed.
  Discover pipeline/version `profile` values are not user profiles and must remain.
- Keep source/relevance coefficients at current defaults, privately owned by retrieval;
  remove personal/profile terms without retuning or renormalizing other terms. Preserve
  current default trusted-source-first ordering (quota 1.0 behavior) without a configurable
  suggestion-mix feature or public ranking-weight model. Scores may change numerically when
  neutral personal/profile offsets disappear; preserve non-personal ordering/eligibility.
- Remove prompt instructions that claim to remember or obey saved preferences. Current-chat
  user instructions and explicit deck intent remain inputs; avoid inventing new memory behavior.
- Remove saved preferences/memory from New Cards context and cache identity; ensure old
  personalized cached advice is not treated as current. Preserve dismissal and run reports.
- Preserve the wrapper-cleanup intent: use the unified Assistant entry point and remove
  redundant Coach pass-throughs if this checkout still contains them. Preserve used analysis.
- Preserve all unrelated staged/unstaged/untracked work. Schema and test fixtures may contain
  Scryfall or live-database safety work; use surgical edits, not file replacement/restoration.
- Follow current `AGENTS.md` and `VERIFY.md`. Live writes affect production. Do not boot or
  switch modes implicitly, change DSNs, run live schema/startup maintenance, or use shared
  data for tests. Validate schema/migration behavior on isolated local PostgreSQL first.
- Add behavioral checks first and prove a relevant check fails under a plausible mutation.
  Remove obsolete feature-only tests; preserve or replace retained behavior coverage at the
  seams above. Mock only external/storage dependencies, not business logic being verified.
- Use VERIFY/AGENTS commands: relevant pytest/Vitest checks, Ruff check/format check,
  `ty check src/`, frontend lint/typecheck and production build. Report unavailable
  database/browser checks as blocked, never as passed.

## Assumptions

- Empty-state copy is English: `Nothing in here yet.` and
  `Profile settings may come in the future.` No placeholder settings or future feature flags.
- Retired endpoints return 404, without deprecated compatibility responses.
- Existing historical chats/runs/traces are not scrubbed; only new operational use of saved
  preferences/memory stops. Already persisted historical advice is not regenerated wholesale.
- Retaining legacy tables, even on fresh initialization for now, is preferable to introducing
  an unapproved data migration; a separate backed-up cleanup can remove them later.
- Live paid model calls are unnecessary for this removal; deterministic adapters exercise
  real application orchestration without sending user data to providers.
- Scope and design were explicitly approved in this conversation on 2026-10-16. The spec
  was missing on `mw/db_migration` and restored on 2026-10-17. Verification instructions
  now reference this checkout's new `VERIFY.md`; product scope and data-retention choices
  are unchanged. The existing blocked report records the earlier failed preflight.

## Milestones

1. Remove persistent memory end to end: Assistant/doctor paths, contracts, editor and obsolete
   tests/scripts; retain conversation/tracing/progress and old storage. Verify AC1–AC3 and AC9.
2. Remove remaining account personalization end to end: recommendation inputs, legacy routes,
   settings UI, pet indicators and persisted Builder rejection; retire old cached context.
   Verify AC4–AC9 and rerun AC1–AC3 for a complete, independently usable release.

## Status

blocked

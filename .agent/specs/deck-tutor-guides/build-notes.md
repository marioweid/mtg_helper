# Build notes — round 3

- `backend/src/mtg_helper/models/tutor.py`: added typed worked-opening-hand output.
- `backend/src/mtg_helper/services/combo_service.py`: reject malformed Commander Spellbook result coverage.
- `backend/src/mtg_helper/services/tutor/{teaching,service,commander,cedh,evidence}.py`: separate command zone,
  validate rendered mainboard hands, specialize mode focus, retain relevant rules, and expose source gaps.
- `backend/tests/test_tutor_guides.py`: added real HTTP/SQL evidence, run, and deletion persistence checks.
- `backend/tests/tutor_fixtures.py`: exposes the exact parent fixture lists without stock-list substitution.
- `frontend/components/tutor-panel.tsx`: polls through repeated running responses and renders verified worked hands.
- `frontend/components/tutor-panel*.test.tsx`, `frontend/lib/types.ts`: covered polling lifecycle and typed guide output.

Gate: Docker affected backend command from `VERIFY.md` plus Tutor/deck/identity/snapshot/source suites.
Final summary: `45 passed in 38.37s`; `All checks passed!`; `257 files already formatted`; `All checks passed!`.
The Docker frontend gate completed earlier this round: 31 files / 127 tests passed; typecheck, lint, format, and
production build passed.

Two full-backend-suite attempts exceeded command time limits and their overlapping one-off containers caused a
transient test-schema deadlock. Both containers were stopped; the final isolated affected gate above is green.
No spec deviation or harness change was made. The existing user edit to `GLOSSARY.md` was preserved unchanged.

## Round 4 — continuation repairs

- `backend/src/mtg_helper/models/tutor.py`: persisted face and typed line-resource/outlet evidence fields.
- `backend/src/mtg_helper/services/tutor/{evidence,teaching,repository}.py`: preserved face/source evidence,
  guarded untrusted teaching context, command-zone instruction, and source-pruning references.
- `backend/src/mtg_helper/services/combo_service.py`: rejected malformed nested Spellbook line entries.
- `backend/src/mtg_helper/{services/card_service.py,services/new_cards/{catalog,discovery}.py,sql/schema.sql}`:
  persisted Scryfall flavor aliases and resolved unambiguous exact aliases before fuzzy matching.
- `backend/src/mtg_helper/services/recommendations/source_repository.py`: retained sources pinned by Tutor runs.
- `backend/tests/{tutor_fixtures,test_tutor_guides,test_deck_import}.py`: added reusable exact fixture data and
  HTTP/SQL regressions for aliases, evidence failures, faces, removal membership, lifecycle, ownership and pruning.
- `frontend/components/tutor-panel.{tsx,test.tsx}`: rendered failed-update last-good freshness/warnings correctly
  and covered source-gap rendering.
- `.agent/specs/deck-tutor-guides/progress.md`: recorded continuation state, verified checks and evaluator setup.

Gate: `docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --workdir
 /workspace/backend ... pytest -q -W error tests/test_tutor_guides.py tests/test_deck_crud.py
 tests/test_deck_import.py tests/test_card_identity_service.py tests/test_snapshots.py tests/test_retrieval_source_tags.py
 ...` -> `92 passed in 73.66s`; Ruff `All checks passed!`; format `257 files already formatted`; Ty `All checks
 passed!`. Frontend `pnpm test && pnpm typecheck && pnpm lint && pnpm format:check && pnpm build` -> `31 passed`,
 `129 passed`, zero lint warnings/errors, format clean, production build compiled successfully.

No harness, live-data, or production change was made. The pre-existing `GLOSSARY.md` edit remains unstaged and
untouched. Live model quality is intentionally not claimed: refresh the isolated Scryfall catalog before exact Blue
Farm import; flavor-name aliases resolve to real canonical facts and expose the parent acceptance-text conflict.

## Round 5 — eval-4 repair

- `backend/src/mtg_helper/models/tutor.py`: retains known card color identity and Commander legality facts in
  frozen Tutor evidence.
- `backend/src/mtg_helper/services/combo_service.py`: validates malformed root, result, optional description,
  bracket, and image source shapes before translation.
- `backend/src/mtg_helper/services/deck_service.py`: serializes quantity and removal writers with Tutor
  publication using the existing deck row lock; category-only metadata remains outside this lock.
- `backend/src/mtg_helper/services/tutor/evidence.py`: distinguishes corrupt rules from unavailable resources,
  pins relevant independent-trigger/devotion rules, and reports known banned/off-color saved cards as warnings.
- `backend/src/mtg_helper/services/tutor/repository.py`: persists manual intent before fallible evidence capture,
  makes state reads read-only, serializes publication against physical list writes, and transfers setup ownership
  to the current authorized owner.
- `backend/src/mtg_helper/services/tutor/teaching.py`: grounds command-zone/rules advice and supplies generic
  exact-list seven-card candidates so the teacher need not invent cards or quantities.
- `backend/tests/tutor_fixtures.py`: corrects the reusable Oracle line to Tainted Pact and supplies exact pinned
  line facts.
- `backend/tests/test_tutor_guides.py`: covers all evaluator malformed payloads, corrupt rules, durable intent,
  selector lifecycle/freshness/persistence matrices, source warnings, real writer race, transfer, and deletion.
- `frontend/components/tutor-panel.tsx`: renders an initial load failure with an explicit retry action.
- `frontend/components/tutor-panel-polling.test.tsx`: covers the initial-load retry state.
- `.agent/specs/deck-tutor-guides/{progress,build-notes}.md`: records this recovery phase and final checks.

Gate: explicit local Docker Compose only. Affected backend source/identity suite
`tests/test_tutor_guides.py tests/test_deck_crud.py tests/test_deck_import.py tests/test_card_identity_service.py
tests/test_snapshots.py tests/test_retrieval_source_tags.py` -> `113 passed in 81.48s`; Ruff `All checks passed!`;
format `257 files already formatted`; Ty `All checks passed!`. Named Tutor selectors: freshness `4 passed`, evidence
`26 passed`, runs `5 passed`, persistence `4 passed`. Frontend: `31` files / `130` tests passed; typecheck passed;
lint `0 warnings and 0 errors`; format clean; production build compiled successfully.

No paid model calls, harness/environment changes, live-data operation, or acceptance-text edit was made. The
pre-existing `GLOSSARY.md` modification remains excluded from this commit. The approved exact-fixture correction
recognizing Rhystic Study, Silence, and Lotus Petal flavor aliases is preserved. Fresh live re-evaluation is pending.

## Round 6 — eval-5 repair

- `backend/src/mtg_helper/models/tutor.py`: added frozen mana/CMC facts and a named structured teacher-output
  shape that deterministically materializes all three persisted hand decisions.
- `backend/src/mtg_helper/services/tutor/teaching.py`: added complete-input byte/card/source limits, mixed
  quantity-valid hand candidates, named-output conversion, and zero model retries.
- `backend/src/mtg_helper/services/tutor/evidence.py`: captures exact mana costs and CMCs without truncating
  Oracle/rule text.
- `backend/src/mtg_helper/services/combo_service.py`: classifies HTTP JSON decoding and non-finite popularity
  as malformed Commander Spellbook responses.
- `backend/src/mtg_helper/services/tutor/repository.py`: prevents a second active teacher for the same deck,
  including after ownership transfer.
- `backend/src/mtg_helper/sql/schema.sql`: safely replaces the old owner-qualified active index and resolves
  pre-upgrade duplicate running rows before reapplication.
- `backend/tests/tutor_fixtures.py`: materializes complete Yuna/Blue Farm lists and real pinned card/face facts
  without reading ignored specs.
- `backend/tests/test_tutor_guides.py`: covers portable fixture integrity, mixed candidates, named output,
  malformed HTTP/overflow coverage, oversized hostile descriptions, transfer interleaving, and index upgrade.
- `backend/tests/test_scryfall_label_schema.py`: isolates its old-tag-table simulation by dropping the local
  dependent view first.
- `.agent/specs/deck-tutor-guides/{progress,build-notes}.md`: records the final scoped repair and checks.

Gate: explicit local Docker Compose only. Affected backend command
`pytest -q -W error tests/test_tutor_guides.py tests/test_deck_crud.py tests/test_deck_import.py
tests/test_card_identity_service.py tests/test_snapshots.py tests/test_retrieval_source_tags.py
tests/test_scryfall_label_schema.py -o cache_dir=/tmp/pytest-cache` -> `122 passed in 95.10s`.
The required no-DB command -> `565 passed, 656 deselected in 9.91s`; Ruff `All checks passed!`; format
`257 files already formatted`; Ty `All checks passed!`. Frontend: `31` files / `130` tests passed;
typecheck passed; lint `0 warnings and 0 errors`; format clean; production build compiled successfully.

No paid calls, source refresh, live-data operation, harness/environment change, or acceptance-text edit was made.
The former supplementary schema failure was a baseline test-fixture dependency; the narrow test-local view drop is
verified by the affected schema suite. The pre-existing `GLOSSARY.md` modification remains unstaged. Fresh live
quality attempts are external evaluator work on the committed repaired HEAD.

## Round 7 - static-review repair completion

- `backend/tests/tutor_fixtures.py`: added portable exact local-catalog facts for Yuna, Grand Summoner and eleven
  actual counter/combat engines, including Oracle identity, mana value/cost, type/text, color identity, and Commander
  legality.
- `backend/tests/test_tutor_guides.py`: added an authenticated Tutor HTTP/evidence consumer that seeds those facts,
  generates a Commander guide without a model call, and verifies Yuna facts plus both shared fixture memberships.
- `frontend/components/tutor-panel.tsx`: split four overlong class/prose literals without changing their rendered
  strings, class order, or state semantics.
- `.agent/specs/deck-tutor-guides/progress.md`: recorded the scoped review repair and red-to-green evidence.

Gate: explicit local Docker Compose only. `tests/test_tutor_guides.py` -> `52 passed in 49.67s`; BackendCheck no-DB
suite -> `565 passed, 657 deselected in 10.10s`; Ruff -> `All checks passed!`; format -> `257 files already formatted`;
Ty -> `All checks passed!`. Frontend `pnpm test` -> `31 passed`, `130 passed`; typecheck passed; lint -> `0 warnings and
0 errors`; format check passed; production build compiled successfully.

No acceptance text, production code, paid call, source refresh, live-data operation, or harness configuration changed.
The pre-existing `GLOSSARY.md` edit remains unstaged and untouched.

## Round 8 — eval-7 repair

- `backend/src/mtg_helper/services/agents/_model.py`: retained the shared `gpt-5.6-luna` default and added a narrow
  keyword-only model override plus the existing Responses high-reasoning type.
- `backend/src/mtg_helper/services/tutor/{teaching,evidence}.py`: selected Tutor-only `gpt-6.1-sol`, high reasoning,
  a 16,000-token one-request/no-tools bound, general resource/timing instructions, CR 302.6 evidence, and a
  seven-copy candidate-work cap without changing frozen quantities.
- `backend/src/mtg_helper/services/deck_service.py`: validates physical additions against the combined Partner
  commander color identity, required to HTTP-seed the genuine complete Blue Farm list.
- `backend/tests/fixtures/tutor_catalog.json`: added 185 real canonical isolated-catalog facts with Oracle identities,
  text, type, mana, color, legality, faces, supplied-name/alias mapping, and catalog-generation provenance.
- `backend/tests/{tutor_fixtures,test_tutor_guides,test_openai_model_config}.py`: loaded the portable catalog; seeded
  complete 99+1 Yuna and 98+2 Blue Farm Tutor runs; checked every identity, quantity and fact including Shelinda,
  Kraum, Tymna and printed aliases; covered Partner color validation, extreme quantity work bounds, and real-agent
  model/settings/usage-limit spies while Coach and Discover remain default-model consumers.
- `.agent/specs/deck-tutor-guides/progress.md`: recorded user-approved Tutor-only model intervention, dataset source,
  repair evidence, and the full-suite baseline result.

Gate: explicit local Docker Compose only. Scoped Tutor/CRUD/OpenAI suite -> `88 passed in 83.43s`; expanded affected
Tutor/CRUD/import/identity/snapshot/source/schema suite -> `141 passed in 99.87s`; no-DB suite -> `567 passed, 662
deselected in 9.93s`; Ruff -> `All checks passed!`; format -> `257 files already formatted`; Ty -> `All checks passed!`.
Frontend -> `31 passed`, `130 passed`; typecheck passed; lint `0 warnings and 0 errors`; format passed; production build
compiled successfully.

The mandated one-time complete backend pytest attempt is recorded honestly: `1192 passed, 10 failed, 27 errors`.
Failures are pre-existing, unrelated full-suite test-isolation/schema assumptions (buylist/price, copy-local host,
stale swap `cards.tags`, duplicate source fixture), so this round does not change unrelated modules or claim that
supplementary command green. All eval-7 scope checks above are green. No paid calls, live-data operation, source
 refresh, environment/volume change, acceptance edit, or fixture fabrication was made; the pre-existing `GLOSSARY.md`
 modification remains unstaged and untouched.

## Round 9 — eval-8 repair

- `backend/src/mtg_helper/models/tutor.py`: raised the typed persisted/model guide limit to 64,000 characters, matching
  the existing 16,000-token Tutor output budget without truncation.
- `backend/src/mtg_helper/services/agents/_model.py`: added an optional isolated SDK retry budget to the existing model
  factory while preserving the shared client/default behavior for ordinary callers.
- `backend/src/mtg_helper/services/tutor/teaching.py`: gives Tutor its owned zero-retry SDK client, closes it after each
  run, and asks for focused 12,000–24,000-character guides below the durable 64,000-character cap.
- `backend/tests/test_openai_model_config.py`: proves Tutor's SDK retry budget is zero while shared Coach/Discover-style
  factory users retain the SDK default, including the real request configuration seam.
- `backend/tests/test_tutor_guides.py`: adds durable detailed-output boundary coverage and real FastAPI/SQL/Pydantic-AI/
  SDK external-boundary checks for HTTP 500, 429, and timeout single-attempt failures, last-good retention, and
  read/same-key idempotency.
- `frontend/components/tutor-panel.test.tsx`: verifies a permitted detailed guide renders completely with existing
  whitespace-preserving word wrapping.
- `.agent/specs/deck-tutor-guides/progress.md`: records eval-8 scope, transport evidence, and scoped verification.

Gate: explicit local Docker Compose only. Expanded affected backend command
`pytest -q -W error tests/test_tutor_guides.py tests/test_deck_crud.py tests/test_deck_import.py
tests/test_card_identity_service.py tests/test_snapshots.py tests/test_retrieval_source_tags.py
tests/test_scryfall_label_schema.py tests/test_openai_model_config.py -o cache_dir=/tmp/pytest-cache` ->
`146 passed in 136.79s`; Ruff -> `All checks passed!`; format -> `257 files already formatted`; Ty -> `All checks
passed!`. Frontend `pnpm test` -> `31 passed`, `131 passed`; typecheck passed; lint -> `0 warnings and 0 errors`;
format passed; production build compiled successfully.

No acceptance text, paid model call, live-data operation, environment/volume change, retry/fallback/critic, or shared
Coach/Discover default changed. The documented 64,000-character cap is deliberately finite and rejects 64,001+
characters; existing frontend wrapping renders it without truncation. The prior unrelated complete-suite baseline was
not rerun. The pre-existing `GLOSSARY.md` modification remains unstaged and untouched.

## Round 10 — standards and approved output-policy repair

- `backend/src/mtg_helper/main.py`: added the standard-envelope handler for expected Tutor failures.
- `backend/src/mtg_helper/models/tutor.py`: removed generated/persisted title, content, and hand-explanation character caps.
- `backend/src/mtg_helper/routers/tutor.py`: routes expected Tutor and email-required failures through the app handler.
- `backend/src/mtg_helper/services/agents/_model.py`: allows callers to omit `max_tokens` without emitting that setting.
- `backend/src/mtg_helper/services/tutor/repository.py`: carries an expected Tutor error code into the app error envelope.
- `backend/src/mtg_helper/services/tutor/teaching.py`: removed Tutor output-token/character targeting while retaining input
  safety and the one-request/no-tools/zero-retry contract.
- `backend/src/mtg_helper/sql/schema.sql`: wrapped the reviewed Tutor-upgrade SQL lines at 100 columns.
- `backend/tests/test_openai_model_config.py`: covers omitted model/usage output caps while preserving Tutor model/retry policy.
- `backend/tests/test_tutor_guides.py`: covers standard Tutor errors, >64,000-character guide and >1,200-character hand
  explanation retention, and outgoing request omission of `max_output_tokens`.
- `frontend/components/tutor-panel.tsx`: wrapped the cEDH explanatory literal at 100 columns without changing output.
- `frontend/components/tutor-panel.test.tsx`: renders an above-64,000-character guide through existing wrapping.
- `.agent/specs/deck-tutor-guides/{progress,build-notes}.md`: records the approved user output policy and round evidence.

Gate: explicit local Docker Compose only. Affected backend suite
`tests/test_tutor_guides.py tests/test_deck_crud.py tests/test_deck_import.py tests/test_card_identity_service.py
tests/test_snapshots.py tests/test_retrieval_source_tags.py tests/test_scryfall_label_schema.py
tests/test_openai_model_config.py` -> `148 passed in 114.64s`; no-DB suite -> `569 passed, 667 deselected in 10.80s`;
Ruff -> `All checks passed!`; format -> `257 files already formatted`; Ty -> `All checks passed!`. Frontend `pnpm test &&
pnpm typecheck && pnpm lint && pnpm format:check && pnpm build` -> `31` files / `131` tests passed, typecheck passed, lint
`0 warnings and 0 errors`, format passed, and production build compiled successfully.

Approved deviation: none. The user explicitly removed application output length/cost constraints for Tutor guides; this
round removes only those output constraints, retains input-safety bounds and provider-native limits, and does not change
Coach/Discover. No paid call, live-data operation, acceptance edit, environment/volume change, or unrelated full backend
suite retry occurred. The pre-existing user-owned `GLOSSARY.md` change remains uncommitted.

## Round 11 — eval-10 request-validation repair

- `backend/src/mtg_helper/routers/tutor.py`: added the Tutor-only route wrapper that turns validation and inherited
  authentication `HTTPException` failures into sanitized standard error envelopes without changing legacy routers.
- `backend/tests/test_tutor_guides.py`: added real FastAPI Tutor HTTP coverage for invalid mode/request key/path UUID,
  missing or malformed JSON, zero persisted intent, and unauthenticated envelope/status behavior.
- `.agent/specs/deck-tutor-guides/progress.md`: recorded the sole eval-10 scope repair, red-to-green result, and narrow
  verification.
- `.agent/specs/deck-tutor-guides/build-notes.md`: recorded this scoped repair and its verification summary.

Gate: explicit local Docker Compose scoped backend verification. `pytest -q -W error tests/test_tutor_guides.py
tests/test_deck_crud.py tests/test_auth.py -o cache_dir=/tmp/pytest-cache` -> `93 passed in 84.12s`; `ruff format .` ->
`257 files left unchanged`; final `ruff format --check .` -> `257 files already formatted`; `ruff check .` and
`ty check src/` -> `All checks passed!`.

No deviation: the requested route-local wrapper is copied from the existing PilotRoute pattern and does not change
global validation/auth behavior. The previously passing paid live runs, unaffected frontend gate, and teacher/model code
were not rerun or modified. `GLOSSARY.md` remains the pre-existing user-owned unstaged change.

## Round 12 — eval-11 parser-base repair

- Tutor catches the documented Starlette HTTP exception base, including invalid-encoding parser
  failures; its FastAPI subclass remains covered. HTTP 400 becomes an actionable sanitized
  `TUTOR_REQUEST_INVALID` response; inherited exception headers and statuses are preserved.
- Added two invalid-UTF-8 HTTP regression cases. Both failed before the fix; both now pass without
  creating setup or generation intent. No teacher, model, evidence, schema or frontend change.
- Final coordinator gate in explicit local Compose: Tutor/CRUD/import/identity/snapshot/source/schema/
  model/auth suite `163 passed in 119.63s`; Ruff, format and Ty clean. The unchanged frontend and
  six paid live-guide passes retain their eval-10 provenance; no replacement paid runs were made.
- Next handoff: independent real-TCP parser check and final static review, then completion report.

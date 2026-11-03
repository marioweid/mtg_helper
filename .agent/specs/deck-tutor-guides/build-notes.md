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

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

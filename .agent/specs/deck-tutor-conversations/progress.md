# Deck Tutor conversations — build progress

- Checkout: `C:\Users\mario\sources\mtg_helper`
- Branch: `ship/deck-tutor-conversations`
- Original BASE / slice-start HEAD: `c2a32e9e70b4c4f7ea10f98438e858920ed1f07d`
- Prerequisite implementation present in start HEAD: saved guides and frozen references, including `a44b0784` and `2e248f8d`.
- Round 1 product HEAD: `826e61e517ccdf151c4e15bf2ce413e5a3352df8` (`spec(deck-tutor-conversations): round 1`).
- Round 2 product HEAD: `94ffc261` (`spec(deck-tutor-conversations): round 2`).
- Current phase: round-3 final-review repairs and explicit local Docker verification complete; ready for the single round-3 local commit.
- User-owned `GLOSSARY.md` modification remains untouched and excluded from staging.

## Delivered acceptance coverage

- AC1/AC2 product path: current-list questions and follow-ups, optional actual-card selection, bounded specialized Commander/cEDH adapters, current evidence instead of stale guide text, unknown-card state, full successful messages on reload.
- AC3: chronological owner-scoped Gesprächskapitel, frozen manifests/evidence, lazy handoffs on the next question or guide action, edit coalescing, no old-chapter reopening, bounded same-chapter compaction plus eight recent turns. Round 3 explicit recovery includes earlier archived learning through successive failed sources, including an empty immediate source.
- AC4: durable request keys, one model execution per key, concurrent-resume chapter/handoff sharing, exact-context/epoch publication checks, terminal failure/superseded/interrupted states, no hidden retry. Round 2 adds an explicit owner-scoped Lernübergabe retry endpoint and accessible button, durable deduplication of duplicate/concurrent retries, safe retries after later context transitions, continued current-fact chat, and interruption/clear barriers. Round 3 shares compaction execution without changing those lifecycles.
- AC5: explicit clear endpoint and UI confirmation, deletion of turns/chapters/handoffs/retry intents, preserved guide/reference storage, epoch barrier against delayed publication.
- AC6: current ownership checks including handoff retry, unauthenticated rejection, current-card evidence and source-gap warnings, hostile history treated as data, chapter source pins retained by pruning, deck deletion cascades.
- AC7: responsive accessible conversation/archive UI, actual current-card options, keyboard send, live status/errors, failure/input retention, explicit failed-handoff retry, clear confirmation, preserved guide/reference workflows.

## Round-3 red/green and final evidence

- The strengthened chained-retry regression was red because compaction received only `After first edit`, not `Original lesson`; the new empty-immediate-source regression was red with HTTP **409**. Both use authenticated HTTP and the real disposable SQL database.
- After walking failed source chapters, the focused selection passed **2 tests**; it passed again after sharing compaction execution/publication between lazy and explicit retry.
- Final affected real-SQL command (`test_tutor_conversations.py`, `test_tutor_guides.py`, `test_tutor_references.py`, `test_deck_crud.py`): **112 passed in 159.90s** against disposable local `mtg_helper_test`.
- Backend `ruff check .`: **all checks passed**.
- Backend `ruff format --check .`: **259 files already formatted**.
- Backend `ty check src/`: **all checks passed**.
- Frontend `pnpm test`: **31 files, 138 tests passed**.
- Frontend `pnpm typecheck`: **passed**.
- Frontend `pnpm lint`: **0 warnings and 0 errors across 148 files**.
- Frontend `pnpm format:check`: **all matched files correctly formatted**.
- Frontend `pnpm build`: **compiled successfully and generated all 16 static pages**.
- Docker AST checks: **109 backend functions** in the three round-3 changed backend/test files; all are ≤100 lines and have ≤5 positional parameters (excluding `self`/`cls`). Ruff complexity checks also pass.
- `git diff --check`: **clean**.
- There is no repository `Makefile`/`make gate`; all verification used explicit local `docker-compose.yml`, with no host checks or live-data configuration.

## Pending acceptance and next action

- Evaluator round 1 passed deterministic/browser AC3–AC7. AC1/AC2 remain **UNVERIFIED** solely for the required configured-live-model three-run semantic scenarios; those calls were not authorized or made in rounds 2–3.
- Next action: create the local round-3 commit excluding `GLOSSARY.md`; do not push or deploy. Live semantic acceptance remains a separately authorized follow-up.

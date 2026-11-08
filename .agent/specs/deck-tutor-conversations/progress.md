# Deck Tutor conversations — build progress

- Checkout: `C:\Users\mario\sources\mtg_helper`
- Branch: `ship/deck-tutor-conversations`
- Original BASE / slice-start HEAD: `c2a32e9e70b4c4f7ea10f98438e858920ed1f07d`
- Prerequisite implementation present in start HEAD: saved guides and frozen references, including `a44b0784` and `2e248f8d`.
- Round 1 product HEAD: `826e61e517ccdf151c4e15bf2ce413e5a3352df8` (`spec(deck-tutor-conversations): round 1`).
- Current phase: round-2 review repairs and explicit local Docker verification complete; ready for the single round-2 local commit.
- User-owned `GLOSSARY.md` modification remains untouched and excluded from staging.

## Delivered acceptance coverage

- AC1/AC2 product path: current-list questions and follow-ups, optional actual-card selection, bounded specialized Commander/cEDH adapters, current evidence instead of stale guide text, unknown-card state, full successful messages on reload.
- AC3: chronological owner-scoped Gesprächskapitel, frozen manifests/evidence, lazy handoffs on the next question or guide action, edit coalescing, no old-chapter reopening, bounded same-chapter compaction plus eight recent turns.
- AC4: durable request keys, one model execution per key, concurrent-resume chapter/handoff sharing, exact-context/epoch publication checks, terminal failure/superseded/interrupted states, no hidden retry. Round 2 adds an explicit owner-scoped Lernübergabe retry endpoint and accessible button, durable deduplication of duplicate/concurrent retries, safe retries after later context transitions, continued current-fact chat, and interruption/clear barriers.
- AC5: explicit clear endpoint and UI confirmation, deletion of turns/chapters/handoffs/retry intents, preserved guide/reference storage, epoch barrier against delayed publication.
- AC6: current ownership checks including handoff retry, unauthenticated rejection, current-card evidence and source-gap warnings, hostile history treated as data, chapter source pins retained by pruning, deck deletion cascades.
- AC7: responsive accessible conversation/archive UI, actual current-card options, keyboard send, live status/errors, failure/input retention, explicit failed-handoff retry, clear confirmation, preserved guide/reference workflows.

## Round-2 red/green and final evidence

- The new real HTTP/SQL handoff-retry regression was red before the route/service seam existed; the rendered UI regression was red because the accessible retry button was absent.
- The retry regression then exposed and fixed concurrent-new-key handling and schema reapplication; the complete conversation file reached `15 passed` before the final combined run.
- Final affected real-SQL command (`test_tutor_conversations.py`, `test_tutor_guides.py`, `test_tutor_references.py`, `test_deck_crud.py`): **111 passed in 152.93s** against disposable local `mtg_helper_test`.
- Backend `ruff check .`: **all checks passed**.
- Backend `ruff format --check .`: **259 files already formatted**.
- Backend `ty check src/`: **all checks passed**.
- Frontend `pnpm test`: **31 files, 138 tests passed**.
- Frontend `pnpm typecheck`: **passed**.
- Frontend `pnpm lint`: **0 warnings and 0 errors across 148 files**.
- Frontend `pnpm format:check`: **all matched files correctly formatted**.
- Frontend `pnpm build`: **compiled successfully and generated all 16 static pages**.
- Docker AST checks: **82 backend functions** in six changed modules and **107 frontend functions** in five changed modules; all are ≤100 lines and have ≤5 positional parameters (excluding `self`/`cls`).
- `git diff --check`: **clean**.
- There is no repository `Makefile`/`make gate`; all verification used explicit local `docker-compose.yml`, with no host checks or live-data configuration.

## Pending acceptance and next action

- Evaluator round 1 passed deterministic/browser AC3–AC7. AC1/AC2 remain **UNVERIFIED** solely for the required configured-live-model three-run semantic scenarios; those calls were not authorized or made in round 2.
- Next action: create the local round-2 commit excluding `GLOSSARY.md`; do not push or deploy. Live semantic acceptance remains a separately authorized follow-up.

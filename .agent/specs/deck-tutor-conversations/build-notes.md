# Build notes — deck-tutor-conversations

## Round-2 changes

- `backend/src/mtg_helper/models/tutor.py`: added the idempotent explicit Lernübergabe retry request contract.
- `backend/src/mtg_helper/routers/tutor.py`: added the owner-scoped chapter handoff retry endpoint with the standard response envelope.
- `backend/src/mtg_helper/services/tutor/repository.py`: bundled chapter capture and shared handoff work, persisted source chapters and deduplicated retry intents, guarded late completion/interruption, and shared source-pin lookup.
- `backend/src/mtg_helper/services/tutor/service.py`: orchestrated explicit retry without automatic paid retries and reused the shared compaction function.
- `backend/src/mtg_helper/services/tutor/commander.py`: removed the compaction pass-through while retaining specialized Commander teaching.
- `backend/src/mtg_helper/services/tutor/cedh.py`: removed the compaction pass-through while retaining specialized cEDH teaching.
- `backend/src/mtg_helper/sql/schema.sql`: added chapter handoff-source tracking and durable, owner/deck/epoch-scoped retry intents with one active retry per chapter.
- `backend/tests/test_tutor_conversations.py`: added real HTTP/SQL failed-handoff retry, duplicate/concurrent deduplication, later-transition/current-fact chat coverage, and retry ownership denial.
- `backend/tests/test_tutor_guides.py`: reused shared Forest identity and deterministic valid-guide fixtures.
- `backend/tests/tutor_fixtures.py`: added the shared Forest identity and valid-guide builder.
- `frontend/lib/api.ts`: added typed explicit handoff-retry transport.
- `frontend/components/tutor-conversation.tsx`: added the accessible retry control and extracted chapter/form/clear rendering to meet function limits.
- `frontend/components/tutor-question-form.tsx`: extracted keyboard/current-card question controls without changing their behavior.
- `frontend/components/tutor-clear-history.tsx`: extracted the existing clear-history confirmation controls.
- `frontend/components/use-tutor-conversation.ts`: centralized conversation state, deduplicated active-work polling, input retention, clear, ask, and explicit handoff retry actions.
- `frontend/components/tutor-panel.tsx`: reduced `TutorPanel`/`TutorPanelView` below 100 lines and connected the retry action while preserving guide/reference workflows.
- `frontend/components/tutor-panel.test.tsx`: added the rendered failed-handoff error and accessible retry-button regression.
- `.agent/specs/deck-tutor-conversations/progress.md`: recorded round-2 red/green evidence, final gate results, and pending live-only acceptance.

## Gate

Explicit local Compose commands from `VERIFY.md`; no `Makefile` or `make gate` exists.

- Backend conversations/guides/references/deck CRUD with disposable `mtg_helper_test`: **111 passed in 152.93s**.
- Backend `ruff check .`: **all checks passed**.
- Backend `ruff format --check .`: **259 files already formatted**.
- Backend `ty check src/`: **all checks passed**.
- Frontend `pnpm test`: **31 files, 138 tests passed**.
- Frontend `pnpm typecheck`: **passed**.
- Frontend `pnpm lint`: **0 warnings and 0 errors across 148 files**.
- Frontend `pnpm format:check`: **all matched files correctly formatted**.
- Frontend `pnpm build`: **compiled successfully; all 16 static pages generated**.
- Docker AST function checks: **82 backend and 107 frontend functions checked; no line/parameter violations**.
- `git diff --check`: **clean**.

## Deviations and remaining acceptance

- No product-scope deviations: no automatic retry, new queue/agent infrastructure, practice controls, global-memory revival, or unrelated refactors.
- Existing user-owned `GLOSSARY.md` edits are intentionally untouched and excluded from this change.
- AC1/AC2 configured-live-model three-run semantic scenarios remain **UNVERIFIED**; no live/paid acceptance calls were authorized or made. Evaluator round-1 deterministic/browser AC3–AC7 results remain the browser evidence for this slice.

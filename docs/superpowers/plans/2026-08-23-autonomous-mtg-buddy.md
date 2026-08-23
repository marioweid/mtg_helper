# Autonomous MTG Buddy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: If available, use the
> `superpowers:subagent-driven-development` skill (recommended); otherwise use the
> `executing-plans` skill to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Make the Commander assistant answer proactively while using theme and card tools as silent,
optional grounding capabilities.

**Architecture:** Retain one Pydantic AI agent with automatic tool choice. Replace the model-visible
theme-first sequence with one typed discovery tool that resolves administrator-managed themes and
silently falls back globally, while structured history preserves grounded card references.

**Tech Stack:** Python 3.13, FastAPI, asyncpg, Pydantic V2, Pydantic AI 2.0, pytest, Next.js,
TypeScript, Vitest

**Spec:** `docs/superpowers/specs/2026-08-23-autonomous-mtg-buddy-design.md`

## Global Constraints

- Keep one Pydantic AI agent and automatic tool choice.
- Add no runtime dependency or database migration.
- Database-ground every actionable card addition.
- Do not expose tool, theme fallback, pipeline, score, or ID terminology to users.
- Ask only when missing information materially changes legality, budget, or strategy.
- Keep Python functions at most 100 lines and lines at most 100 characters.

---

### Task 1: Unified Card Discovery

**Files:**
- Modify: `backend/src/mtg_helper/services/mtg_card_search.py`
- Test: `backend/tests/test_mtg_card_search.py`

**Interfaces:**
- Produces: `AssistantCardDiscoveryInput`, accepted by `search_cards(...)`.
- Preserves: `CardSearchResult` and `CardSearchCandidate` grounding contracts.

- [ ] Write failing tests proving natural theme hints resolve administrator groups, unresolved hints
  fall back globally, empty theme pools fall back globally, and fallback does not require caller
  confirmation.
- [ ] Run `uv run pytest -q tests/test_mtg_card_search.py` and confirm the new tests fail.
- [ ] Add a natural-language query and theme hints to the typed input, resolve all hints internally,
  merge explicit resolved tags with relevant deck tags, and preserve structural filters.
- [ ] Keep global fallback internal and return typed provenance without a user-directed clarification
  message.
- [ ] Run `uv run pytest -q tests/test_mtg_card_search.py` and confirm it passes.

### Task 2: Autonomous Agent Policy

**Files:**
- Modify: `backend/src/mtg_helper/services/mtg_assistant.py`
- Test: `backend/tests/test_commander_coach_pipeline.py`

**Interfaces:**
- Consumes: `AssistantCardDiscoveryInput` from Task 1.
- Produces: model-visible `find_cards(ctx, request) -> CardSearchResult`.

- [ ] Write failing tests asserting the agent exposes `find_cards` instead of `search_themes`, the
  prompt permits direct answers, clarification is decision-blocking only, and internal fallback
  narration is forbidden.
- [ ] Add a boundary test capturing `Agent.run(...)` arguments and proving grounded prior references
  are loaded before the run.
- [ ] Run the focused assistant tests and confirm the new tests fail.
- [ ] Replace the procedural prompt with the approved MTG buddy identity and grounding policy.
- [ ] Replace `search_themes` and `search_cards` model tools with `find_cards`, retaining inspection,
  analysis, legality, bracket, and bounded usage.
- [ ] Make timeout/tool-limit fallback synthesize from available evidence when possible and use a
  concise recoverable response otherwise.
- [ ] Run the focused assistant tests and confirm they pass.

### Task 3: Grounded Conversation References

**Files:**
- Modify: `backend/src/mtg_helper/models/ai.py`
- Modify: `backend/src/mtg_helper/services/mtg_assistant.py`
- Test: `backend/tests/test_commander_coach_pipeline.py`

**Interfaces:**
- Produces: optional `CoachHistoryTurn.recommendations: list[CoachHistoryCardReference]`.
- Consumes: reference IDs/names in assistant dependencies and prompt payload.

- [ ] Write failing contract tests for valid references, malformed IDs, history serialization, and
  follow-up reuse of a previously grounded card.
- [ ] Run the focused tests and confirm they fail.
- [ ] Add the typed optional history references without changing existing callers.
- [ ] Seed the per-run grounded map from history references only when their IDs and names correspond
  to cards represented in prior assistant turns.
- [ ] Include compact recent recommendation references in the prompt payload.
- [ ] Run the focused tests and confirm they pass.

### Task 4: User-Centered Progress

**Files:**
- Create: `frontend/lib/coach-progress.ts`
- Create: `frontend/lib/coach-progress.test.ts`
- Modify: `frontend/app/decks/[id]/coach/page.tsx`

**Interfaces:**
- Produces: `coachProgressMessage(event: CoachEvent): string | null`.
- Produces: one replaceable progress string in page state.

- [ ] Write failing tests proving internal memory/routing/done events are hidden and useful work
  events map to concise user-facing messages.
- [ ] Run `corepack pnpm test -- lib/coach-progress.test.ts` and confirm failure.
- [ ] Implement the pure progress mapping and replace the accumulated timeline with one status.
- [ ] Remove raw event identifiers and tool-call counts from the normal assistant presentation.
- [ ] Run focused frontend tests and confirm they pass.

### Task 5: Frontend Structured History

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/coach-conversation.ts`
- Modify: `frontend/lib/coach-conversation.test.ts`
- Modify: `frontend/app/decks/[id]/coach/page.tsx`

**Interfaces:**
- Consumes: response recommendation card IDs and names.
- Produces: bounded request history carrying assistant recommendation references.

- [ ] Write failing tests proving references remain attached to assistant turns, survive history
  bounding, and are absent from user turns.
- [ ] Run the focused conversation tests and confirm failure.
- [ ] Extend frontend types and history construction with optional grounded references.
- [ ] Record each completed assistant response with its recommendation references.
- [ ] Run the focused frontend tests and confirm they pass.

### Task 6: Executable Quality Evaluation

**Files:**
- Modify: `backend/evals/assistant_quality_cases.json`
- Modify: `backend/scripts/eval_assistant_quality.py`
- Modify: `backend/tests/test_assistant_quality_eval.py`

**Interfaces:**
- Produces: deterministic scoring for captured tool calls, clarification behavior, grounded
  recommendations, forbidden process language, and multi-turn references.

- [ ] Replace the old clarification-rewarding cases with direct-answer, silent-fallback,
  zero-tool-strategy, grounded-card, follow-up-reference, and bracket scenarios.
- [ ] Write failing evaluator tests for expected/forbidden tools, maximum clarification count, and
  recommendation grounding.
- [ ] Run the evaluator tests and confirm failure.
- [ ] Extend the evaluator schema and scorer for observable run records while preserving corpus
  validation mode.
- [ ] Run evaluator tests and `uv run python scripts/eval_assistant_quality.py --validate`.

### Task 7: Integration and Quality Gates

**Files:**
- Test: backend and frontend files modified above

**Interfaces:**
- Verifies all preceding tasks against the approved spec.

- [ ] Run focused backend assistant, search, theme, and evaluation tests.
- [ ] Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check src/`.
- [ ] Run `uv run pytest -q -m no_db` and database tests when Docker is available.
- [ ] Run `corepack pnpm test`, `corepack pnpm typecheck`, `corepack pnpm lint`, and
  `corepack pnpm format:check`.
- [ ] Run `corepack pnpm build` and record any dependency warnings separately from failures.
- [ ] Review the final diff against every design principle and remove procedural narration,
  compatibility code without a concrete consumer, and unnecessary abstractions.

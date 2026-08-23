# Conversational MTG Assistant Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: If available, use the
> `superpowers:subagent-driven-development` skill (recommended); otherwise use the
> `executing-plans` skill to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Make the unified MTG Assistant produce confident, deck-aware conversational advice while
preserving deterministic grounding and exact card verification.

**Architecture:** Keep the single Pydantic AI assistant and add role-aware message history, a compact
complete-deck briefing, and one current-deck inspection tool. Extend normal chat responses with
grounded recommendation cards, narrow deterministic memory interception, and evaluate behavior with
versioned fixtures rather than introducing another model pipeline.

**Tech Stack:** Python 3.13, FastAPI, Pydantic V2, Pydantic AI 1.71, OpenAI Responses, pytest, Next.js
15 App Router, React 19, TypeScript 5.8, Vitest, pnpm.

**Spec:** `docs/superpowers/specs/2026-08-23-conversational-mtg-assistant-quality-design.md`

## Global Constraints

- Keep one unified `mtg_assistant` model run per normal turn.
- Keep the fixed OpenAI Responses model and `openai_store=False`.
- Do not add fine-tuning, model routing, chat persistence, or a specialist fallback.
- Every actionable addition must come from current-run deterministic retrieval.
- Keep Python functions at 100 lines or fewer, complexity at 8 or lower, and lines at 100 characters.
- Use absolute Python imports and Google-style docstrings for non-trivial public APIs.
- Use TDD for every behavior change.
- Do not change the separate `/doctor` endpoint.

---

### Task 1: Typed Conversation And Recommendation Contracts

**Files:**
- Modify: `backend/src/mtg_helper/models/ai.py:436-480`
- Modify: `frontend/lib/types.ts:672-751`
- Test: `backend/tests/test_commander_coach_pipeline.py`

**Interfaces:**
- Produces: `CoachHistoryTurn(role: Literal["user", "assistant"], content: str)`.
- Produces: `CommanderCoachRequest.history: list[CoachHistoryTurn]`.
- Produces: `CommanderCoachResponse.recommendations: list[ReplacementOption]`.
- Consumes later: Tasks 2, 3, and 5 pass `history` and render `recommendations`.

- [ ] **Step 1: Add failing backend contract tests**

Add tests asserting valid role-aware history, rejected empty content, rejected unknown roles, bounded
turn count, and the default empty recommendation list:

```python
def test_coach_request_accepts_role_aware_history() -> None:
    request = CommanderCoachRequest(
        message="What should I add for draw?",
        history=[
            {"role": "user", "content": "Keep this Food-first."},
            {"role": "assistant", "content": "I will prioritize Food engines."},
        ],
    )

    assert [turn.role for turn in request.history] == ["user", "assistant"]
    assert request.message == "What should I add for draw?"


def test_coach_response_defaults_to_no_recommendations() -> None:
    response = CommanderCoachResponse(mode="chat", reply="Answer")
    assert response.recommendations == []
```

Use `pytest.raises(ValidationError)` cases for blank `message`, blank history content, an unsupported
role, and more than 12 history turns. Set `message` to `Field(min_length=1, max_length=4000)` and
history content to `Field(min_length=1, max_length=4000)`.

- [ ] **Step 2: Run the contract tests and confirm failure**

Run:

```powershell
uv run pytest -q tests/test_commander_coach_pipeline.py -k "history or recommendations"
```

Expected: failures because `CoachHistoryTurn`, `history`, and response recommendations do not exist.

- [ ] **Step 3: Implement the backend and frontend types**

Add the backend model:

```python
class CoachHistoryTurn(BaseModel):
    """One completed visible turn supplied as recent conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
```

Change `CommanderCoachRequest.message` to require non-empty content and add:

```python
history: list[CoachHistoryTurn] = Field(default_factory=list, max_length=12)
```

Add this field to `CommanderCoachResponse`:

```python
recommendations: list[ReplacementOption] = Field(default_factory=list, max_length=8)
```

Mirror the contract in TypeScript:

```typescript
export interface CoachHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface CommanderCoachRequest {
  message: string;
  history?: CoachHistoryTurn[];
  mode?: CommanderCoachMode;
  coach_memory_notes?: string | null;
}
```

Add `recommendations: ReplacementOption[]` to `CommanderCoachResponse`.

- [ ] **Step 4: Run focused backend tests**

Run:

```powershell
uv run pytest -q tests/test_commander_coach_pipeline.py -k "history or recommendations"
```

Expected: pass.

- [ ] **Step 5: Commit the contract change**

```powershell
git add backend/src/mtg_helper/models/ai.py backend/tests/test_commander_coach_pipeline.py frontend/lib/types.ts
git commit -m "Add structured coach conversation contracts"
```

---

### Task 2: Complete Deck Briefing And Card Inspection

**Files:**
- Create: `backend/src/mtg_helper/services/assistant_deck_context.py`
- Modify: `backend/src/mtg_helper/services/mtg_assistant.py:15-217`
- Create: `backend/tests/test_assistant_deck_context.py`
- Modify: `backend/tests/test_commander_coach_pipeline.py`

**Interfaces:**
- Consumes: `DeckDetailResponse` and its enriched `DeckCardItem` score fields.
- Produces: `build_deck_briefing(deck: DeckDetailResponse) -> dict[str, object]`.
- Produces: `inspect_deck_cards(deck: DeckDetailResponse, names: list[str]) -> DeckCardInspection`.
- Produces: Pydantic models `InspectedDeckCard` and `DeckCardInspection`.
- Consumes later: Task 3 includes the briefing in the user payload and registers the inspection tool.

- [ ] **Step 1: Write failing deck-context tests**

Create a fixture with commander, partner, role targets, description, and at least three deck cards
with different score/protection values. Assert the briefing includes every card but excludes Oracle
text from manifest rows:

```python
def test_build_deck_briefing_contains_complete_compact_manifest() -> None:
    briefing = build_deck_briefing(_deck())
    cards = briefing["cards"]

    assert {card["name"] for card in cards} == {
        "Food Engine",
        "Skullclamp",
        "Weak Value Card",
    }
    assert all("oracle_text" not in card for card in cards)
    assert cards[0].keys() >= {
        "name",
        "quantity",
        "mana_value",
        "type_line",
        "categories",
        "tags",
        "deck_fit_score",
        "deck_fit_band",
        "deck_fit_reasons",
        "deck_fit_protected",
    }
```

Add inspection tests for case-insensitive matching, exact Oracle text, preserved score evidence,
deduplicated names, a maximum of eight requested names, and explicit unknown names.

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
uv run pytest -q tests/test_assistant_deck_context.py
```

Expected: import failure because the context module does not exist.

- [ ] **Step 3: Implement focused deck-context models and functions**

Create Pydantic result models:

```python
class InspectedDeckCard(BaseModel):
    name: str
    mana_cost: str | None
    mana_value: float | None
    type_line: str | None
    oracle_text: str | None
    quantity: int
    categories: list[str]
    tags: list[str]
    deck_fit_score: int | None
    deck_fit_band: Literal["strong", "solid", "weak"] | None
    deck_fit_reasons: list[str]
    deck_fit_protected: bool


class DeckCardInspection(BaseModel):
    cards: list[InspectedDeckCard]
    unknown_names: list[str]
```

Implement `build_deck_briefing()` with bounded lists: at most eight tags/categories per card and
three fit reasons. Derive role counts, type counts, and curve using small module-level functions so
no function exceeds project limits. Include `stage_targets` unchanged and sort manifest rows by
mana value then name.

Implement `inspect_deck_cards()` with a hard eight-name cap, case-insensitive matching, request-order
preservation, and no database or global search.

- [ ] **Step 4: Register a failing agent-tool test**

In `test_commander_coach_pipeline.py`, configure `TestModel(call_tools=["inspect_deck_cards"])` and
assert the tool exists in `function_tools`, returns exact Oracle text, and increments
`AssistantDeps.tool_calls` once.

- [ ] **Step 5: Add the assistant tool wrapper**

Import the context service and register:

```python
async def inspect_current_deck_cards(
    ctx: RunContext[AssistantDeps], names: list[str]
) -> DeckCardInspection | None:
    """Return exact text and fit evidence for up to eight current-deck cards."""
    if not ctx.deps.allow_tool():
        return None
    return inspect_deck_cards_service(ctx.deps.deck, names)
```

Name the registered tool `inspect_deck_cards` by using that function name or an explicit Pydantic AI
tool name. Add it to the agent tool list without changing the six-call budget.

- [ ] **Step 6: Run context and pipeline tests**

Run:

```powershell
uv run pytest -q tests/test_assistant_deck_context.py tests/test_commander_coach_pipeline.py
```

Expected: pass.

- [ ] **Step 7: Commit deck context and inspection**

```powershell
git add backend/src/mtg_helper/services/assistant_deck_context.py backend/src/mtg_helper/services/mtg_assistant.py backend/tests/test_assistant_deck_context.py backend/tests/test_commander_coach_pipeline.py
git commit -m "Give assistant complete deck context"
```

---

### Task 3: Role-Aware Agent Run And Coaching Prompt

**Files:**
- Modify: `backend/src/mtg_helper/services/mtg_assistant.py:61-359`
- Modify: `backend/src/mtg_helper/services/agents/_history.py:12-31`
- Modify: `backend/src/mtg_helper/services/agents/_model.py:3-31`
- Modify: `backend/tests/test_commander_coach_pipeline.py`
- Modify: `backend/tests/test_openai_model_config.py`

**Interfaces:**
- Consumes: `CommanderCoachRequest.history` from Task 1.
- Consumes: `build_deck_briefing()` and inspection tool from Task 2.
- Produces: `_bounded_history(request: CommanderCoachRequest) -> list[ModelMessage]`.
- Produces: `openai_model_settings(..., verbosity: Literal["low", "medium"] = "low")`.
- Produces: chat responses with validated `CommanderCoachResponse.recommendations`.
- Consumes later: Task 5 sends structured history and renders recommendations.

- [ ] **Step 1: Add failing role-aware history tests**

Add a test model run with two history turns and inspect `model.last_model_request_parameters` or the
captured model messages. Assert prior user and assistant turns are represented by `ModelRequest` and
`ModelResponse`, while the latest `request.message` appears exactly once as the new prompt.

Add a pure test for `_bounded_history()` with 12 turns whose aggregate content exceeds 12,000
characters. Assert it retains the newest complete turns in chronological order and never retains an
assistant turn whose preceding user turn was dropped. Use constants:

```python
_MAX_HISTORY_TURNS = 12
_MAX_HISTORY_CHARACTERS = 12_000
```

- [ ] **Step 2: Run history tests and confirm failure**

Run:

```powershell
uv run pytest -q tests/test_commander_coach_pipeline.py -k "message_history or bounded_history"
```

Expected: failure because the run does not pass `message_history`.

- [ ] **Step 3: Implement bounded history and agent wiring**

Convert typed turns to dictionaries at the existing `_history.to_model_messages()` boundary. Pass
the result as `message_history=` and pass only `request.message` plus current deck/preferences in the
new run prompt. Remove all transcript marker parsing from the assistant path.

Replace `_prompt_payload()` with a payload containing:

```python
{
    "current_request": request.message,
    "deck": build_deck_briefing(deck),
    "preferences": (request.coach_memory_notes or "")[-8000:],
}
```

The current request remains in the payload because it is the current user prompt; it must not also
appear in `message_history`.

- [ ] **Step 4: Add failing prompt and response-grounding tests**

Assert the prompt payload includes all fixture card names, scores, role targets, commander Oracle
text, and memory. Add a chat-mode test with one retrieved recommendation and one unknown ID; assert
the response retains only the grounded recommendation in `response.recommendations` while keeping
`doctor` and `replacement` unset.

- [ ] **Step 5: Replace the system prompt**

Rewrite `_SYSTEM_PROMPT` with these explicit sections and rules:

```text
ROLE
You are a confident but verified Commander deck-building partner.

COACHING WORKFLOW
Understand the commander's game plan and the user's stated direction. Inspect what the deck already
contains. Answer the current question directly. Give a small ranked package, explain interactions
with the commander and existing cards, state tradeoffs, and identify what to add or change first.
Do not ask for facts already present in the deck briefing, memory, or conversation.

VERIFICATION
Recommended additions must come from search_cards in this run. Inspect exact Oracle text before
asserting a current-deck card interaction. For a repeatable or infinite loop, account for starting
resources, every cost and trigger, resources produced, how the state resets, and the payoff. Never
call a loop infinite while a required resource decreases each iteration.

TOOLS AND OUTPUT
Use inspect_deck_cards for exact text of current cards, analyze_deck for diagnosis/cuts/swaps,
analyze_mana_base for mana requests, check_legality for legality, and check_bracket for bracket
guidance. Preserve existing typed-search and theme-search restrictions. Use chat for natural advice,
doctor for whole-deck changes, and replacement for one named target.
```

Retain the detailed existing search constraints, grounding rule, theme ambiguity behavior, mana-base
workflow, and rules-lookup limitation after these behavioral sections.

- [ ] **Step 6: Add assistant-specific model-setting tests**

Change the helper test to assert the default remains low verbosity for other workflows and add:

```python
settings = openai_model_settings(max_tokens=4096, reasoning="low", verbosity="medium")
assert settings["openai_text_verbosity"] == "medium"
```

Assert `mtg_assistant` uses 4,096 output tokens and medium verbosity while all other builders retain
their existing settings.

- [ ] **Step 7: Implement workflow-specific verbosity and response mapping**

Add `TextVerbosity = Literal["low", "medium"]`, default `verbosity="low"`, and pass it to
`openai_text_verbosity`. Configure only `mtg_assistant` with 4,096 tokens and medium verbosity.

Build grounded `ReplacementOption` objects once in `_to_response()`. Attach them to the top-level
response in all modes. Keep chat free of cuts/swaps, and reuse the same options in replacement mode
without weakening existing target validation.

- [ ] **Step 8: Run agent, model, and run-contract tests**

Run:

```powershell
uv run pytest -q tests/test_commander_coach_pipeline.py tests/test_openai_model_config.py tests/test_agent_run_contracts.py
```

Expected: pass.

- [ ] **Step 9: Commit assistant behavior**

```powershell
git add backend/src/mtg_helper/services/mtg_assistant.py backend/src/mtg_helper/services/agents/_history.py backend/src/mtg_helper/services/agents/_model.py backend/tests/test_commander_coach_pipeline.py backend/tests/test_openai_model_config.py
git commit -m "Improve grounded assistant conversations"
```

---

### Task 4: Explicit Memory Command Routing

**Files:**
- Modify: `backend/src/mtg_helper/services/coach_memory_service.py:121-280`
- Modify: `backend/tests/test_coach_memory.py`

**Interfaces:**
- Consumes: latest `CommanderCoachRequest.message` only; structured history is not parsed for
  commands.
- Produces: `handle_memory_message(...)` returns a response only for explicit show/add/remove memory
  commands.
- Preserves: memory CRUD and explicit command responses.

- [ ] **Step 1: Replace preference-interception expectations with failing behavior tests**

Keep explicit tests for "What do you have in memory?", "Remember that I hate counterspells", and
"Remove the memory note about counterspells". Replace self-detection assertions with pure service
tests that patch `get_memory` and assert these return `None`:

```python
@pytest.mark.parametrize(
    "message",
    [
        "I hate counterspells",
        "I prefer Food win conditions; what draw should I add?",
        "Please avoid tutors and suggest three replacements",
        "For Yuna I also want counters other than +1/+1 counters",
    ],
)
async def test_preference_bearing_questions_reach_assistant(message: str) -> None:
    result = await handle_memory_message(pool, deck_id, account_id, CommanderCoachRequest(message=message))
    assert result is None
```

- [ ] **Step 2: Run memory tests and confirm failure**

Run:

```powershell
uv run pytest -q tests/test_coach_memory.py
```

Expected: preference messages are currently intercepted and fail the new assertions.

- [ ] **Step 3: Remove implicit note detection and transcript parsing**

Delete `_latest_user_text()` and `_looks_like_memory_note()`. Use `request.message.strip()` directly.
Restrict add intent to explicit phrases beginning with `remember`, `remember that`, `add to memory`,
`save to memory`, or `note that`. Restrict removal to explicit `forget`, `delete from memory`,
`remove from memory`, or a remove request that explicitly contains `memory`. Keep show intent based
on explicit memory wording.

Do not automatically persist preference-bearing deck questions in this change.

- [ ] **Step 4: Run memory tests**

Run:

```powershell
uv run pytest -q tests/test_coach_memory.py
```

Expected: pass.

- [ ] **Step 5: Commit memory routing**

```powershell
git add backend/src/mtg_helper/services/coach_memory_service.py backend/tests/test_coach_memory.py
git commit -m "Limit coach memory routing to explicit commands"
```

---

### Task 5: Frontend Structured History And Chat Recommendations

**Files:**
- Create: `frontend/lib/coach-conversation.ts`
- Create: `frontend/lib/coach-conversation.test.ts`
- Modify: `frontend/app/decks/[id]/coach/page.tsx:1-545`
- Modify: `frontend/lib/types.ts:710-751`
- Create: `frontend/components/coach-recommendations.tsx`
- Create: `frontend/components/coach-recommendations.test.tsx`

**Interfaces:**
- Consumes: `CoachHistoryTurn` and `CommanderCoachResponse.recommendations` from Task 1.
- Produces: `buildCoachHistory(messages: CoachMessage[]): CoachHistoryTurn[]`.
- Produces: `CoachRecommendations({ recommendations }: Props)`.
- Preserves: existing SSE, doctor, replacement, and memory rendering.

- [ ] **Step 1: Write failing structured-history tests**

Move the minimal conversation type to the new module or expose a simple input type:

```typescript
export interface VisibleCoachTurn {
  role: "user" | "assistant";
  content: string;
}
```

Test that `buildCoachHistory()`:

- returns completed turns in role order;
- returns at most 12 turns;
- stays within 12,000 characters by removing oldest complete user/assistant pairs;
- never includes the latest unsent textarea content;
- preserves assistant reply text rather than structured UI data.

- [ ] **Step 2: Run the history test and confirm failure**

Run:

```powershell
pnpm test -- lib/coach-conversation.test.ts
```

Expected: module import failure.

- [ ] **Step 3: Implement the history builder and request change**

Implement constants matching the backend and a pair-aware oldest-first truncation loop. Replace
`transcriptWith()` in `page.tsx` with:

```typescript
const history = buildCoachHistory(
  messages.map((turn) => ({
    role: turn.role,
    content: turn.role === "user" ? turn.content : turn.result.reply,
  })),
);

await apiClient.startCoachDeck(deckId, {
  mode: "auto",
  message: content,
  history,
});
```

Do not include the newly appended optimistic user message because React state still contains only
completed prior turns at request construction time.

- [ ] **Step 4: Write failing recommendation renderer tests**

Create a card fixture and assert the component renders card name, reason, role match, and tradeoff.
Assert an empty list renders nothing. Use existing card visual primitives if one already accepts
`AnalysisCardHit`; otherwise render a focused list with the established Coach typography and card
image/name behavior from `page.tsx`.

- [ ] **Step 5: Implement and integrate recommendation rendering**

Create `CoachRecommendations` with a flat list of cards. Render it in `AssistantMessage` for normal
chat and any mode where top-level recommendations are present. Avoid duplicating the same cards when
the replacement panel already renders `replacement.options`; skip the generic component in
replacement mode. Preserve doctor rendering and existing mobile layout.

- [ ] **Step 6: Add a request-shape integration test at the utility boundary**

In `coach-conversation.test.ts`, model two completed turns plus a latest prompt and assert the
constructed request object has separate `message` and `history`, with no `User:`/`Assistant:` marker
text. This utility-level test avoids mocking `EventSource` and Next routing for behavior owned by the
pure history builder.

- [ ] **Step 7: Run frontend tests and checks**

Run:

```powershell
pnpm test -- lib/coach-conversation.test.ts components/coach-recommendations.test.tsx
pnpm typecheck
pnpm lint
pnpm format:check
```

Expected: all pass with no warnings.

- [ ] **Step 8: Commit frontend behavior**

```powershell
git add frontend/lib/coach-conversation.ts frontend/lib/coach-conversation.test.ts frontend/components/coach-recommendations.tsx frontend/components/coach-recommendations.test.tsx frontend/app/decks/[id]/coach/page.tsx frontend/lib/types.ts
git commit -m "Use structured assistant conversation history"
```

---

### Task 6: Versioned Assistant Quality Evaluation

**Files:**
- Create: `backend/evals/assistant_quality_cases.json`
- Create: `backend/scripts/eval_assistant_quality.py`
- Create: `backend/tests/test_assistant_quality_eval.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces: `AssistantEvalCase` and `AssistantEvalResult` Pydantic models in the script.
- Produces: `load_cases(path: Path) -> list[AssistantEvalCase]`.
- Produces: `score_response(case: AssistantEvalCase, response: CommanderCoachResponse) -> AssistantEvalResult`.
- Consumes: existing `run_assistant()` only when invoked with `--live`.

- [ ] **Step 1: Write failing fixture-schema and deterministic scorer tests**

Test that all ten required case IDs load, IDs are unique, every case has required/forbidden
characteristics, and the deterministic scorer catches forbidden text case-insensitively. Include the
Camellia invalid-loop case with forbidden claims such as:

```json
{
  "id": "camellia-altar-invalid-two-card-loop",
  "required_phrases": ["Peregrin Took"],
  "forbidden_phrases": [
    "Camellia + Ashnod's Altar is infinite",
    "replacement Food"
  ]
}
```

Do not assert exact answer prose. The deterministic scorer covers observable requirements and
forbidden claims; qualitative dimensions remain rubric fields for recorded human/model review.

- [ ] **Step 2: Run evaluation tests and confirm failure**

Run:

```powershell
uv run pytest -q tests/test_assistant_quality_eval.py
```

Expected: missing evaluation script and fixture.

- [ ] **Step 3: Create all ten versioned cases**

Add cases for Food win conditions, the draw follow-up, already-present card awareness, replacement,
mana, memory budget, no infinites, invalid Camellia/Altar loop, ambiguous theme, and ungrounded
recommendation. Each case includes:

```json
{
  "id": "stable-slug",
  "deck_fixture": "camellia_food",
  "history": [],
  "message": "...",
  "memory": "...",
  "expected_tools": [],
  "required_phrases": [],
  "forbidden_phrases": [],
  "rubric": ["deck_awareness", "continuity", "grounding", "correctness", "actionability"]
}
```

- [ ] **Step 4: Implement deterministic loading/scoring and an explicit live mode**

The default command validates cases only and performs no network request. `--live` requires
`OPENAI_API_KEY` and a configured database/deck fixture source, runs cases sequentially, and writes a
timestamped JSON report under `backend/evals/results/`, which must be gitignored. Record model name,
case ID, token usage already exposed by telemetry where available, response mode, required/forbidden
checks, and rubric fields. Never record API keys or production conversation content.

Register a pytest marker:

```toml
markers = [
    "no_db: test does not require the PostgreSQL test database",
    "ai_eval: opt-in model-backed assistant quality evaluation",
]
```

The ordinary pytest suite tests only fixture validation and deterministic scoring.

- [ ] **Step 5: Run evaluation tests and fixture validation**

Run:

```powershell
uv run pytest -q tests/test_assistant_quality_eval.py
uv run python scripts/eval_assistant_quality.py --validate
```

Expected: pass and print ten valid case IDs without a network request.

- [ ] **Step 6: Commit the evaluation harness**

```powershell
git add backend/evals/assistant_quality_cases.json backend/scripts/eval_assistant_quality.py backend/tests/test_assistant_quality_eval.py backend/pyproject.toml .gitignore
git commit -m "Add assistant quality evaluation cases"
```

---

### Task 7: End-To-End Verification And Documentation Sync

**Files:**
- Modify if required by actual behavior: `docs/superpowers/specs/2026-08-23-conversational-mtg-assistant-quality-design.md`
- Modify if user-facing setup changed: `README.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: a verified feature branch ready for review.

- [ ] **Step 1: Run focused backend behavior tests**

```powershell
uv run pytest -q tests/test_assistant_deck_context.py tests/test_commander_coach_pipeline.py tests/test_coach_memory.py tests/test_openai_model_config.py tests/test_agent_run_contracts.py tests/test_assistant_quality_eval.py
```

Expected: pass.

- [ ] **Step 2: Run all backend quality gates**

```powershell
uv run ruff check .
uv run ruff format --check .
uv run ty check src/
uv run pytest -q
```

Expected: pass with no warnings. If database-backed tests require unavailable infrastructure, run
the documented Docker Compose test setup; do not claim the suite passed without it.

- [ ] **Step 3: Run all frontend quality gates**

```powershell
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

Expected: pass with no warnings.

- [ ] **Step 4: Review the final diff against the spec**

Run:

```powershell
git status --short
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
```

Confirm no fine-tuning, router, conversation table, provider storage, score-formula change, or
separate `/doctor` change entered the diff. Confirm the request no longer constructs flattened
`User:`/`Assistant:` transcripts.

- [ ] **Step 5: Update documentation only for observed final behavior**

If implementation differs from the approved spec, update the spec to describe the resulting public
contract before review. Update `README.md` only if users or operators gained a command or setup
requirement; do not document the internal evaluation command as production behavior.

- [ ] **Step 6: Commit any verification-driven documentation corrections**

```powershell
git add docs/superpowers/specs/2026-08-23-conversational-mtg-assistant-quality-design.md README.md
git diff --cached --quiet; if (-not $?) { git commit -m "Document assistant conversation behavior" }
```

- [ ] **Step 7: Push the completed branch**

```powershell
git push origin feat/conversational-assistant-quality
```

Report focused and full verification separately, including any command that could not run and its
exact blocker.

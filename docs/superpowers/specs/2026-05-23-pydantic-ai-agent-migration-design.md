# Pydantic AI Agent Migration — Design

Date: 2026-05-23
Status: Approved (pending user review)

## Context

The codebase has three LLM-driven agents:

1. `simulation_analysis_service.analyze_simulation` — already on
   `pydantic-ai` with `GoogleModel`, a `card_search` tool, and structured
   `output_type=SimulationAnalysisResponse`.
2. `ai_service.describe_deck` — conversational deck-strategy agent.
   Still uses `LLMClient.chat()` (raw text) and parses a sentinel
   `{"done": true, ...}` JSON block out of the model's reply with a
   greedy `json.JSONDecoder` scan.
3. `ai_service.extract_keywords` — same pattern, emits archetype tags.

Migrating (2) and (3) onto `pydantic-ai` removes ~250 lines of
prompt-assembly and regex parsing in favor of an `output_type`-enforced
Pydantic schema (the SDK validates and re-prompts on shape errors).
While we're touching agent code, we also share the model-construction
helper across all three agents so they stay consistent.

`pydantic-ai-slim[google]==1.71.0` is already a dependency.

Out of scope: embeddings. `LLMClient.embed()` stays — `pydantic-ai` is
agent-loop-oriented, not a batch embedding pipeline.

## Goals

- `describe_deck` and `extract_keywords` run on `pydantic-ai`, returning
  the existing `DescribeResponse` / `KeywordExtractResponse` schemas
  natively from the model (no regex parsing).
- Conversation history is replayed via `pydantic-ai`'s native
  `message_history` (`ModelRequest` / `ModelResponse`) instead of
  inlining role-tagged text into prompts.
- All three agents construct their `GoogleModel` through a single
  helper.
- `LLMClient` shrinks to just `embed()`; `chat()`, `chat_with_tools()`,
  `ToolCall`, `ChatToolResponse` are deleted (unused after the
  migration).
- One happy-path test per new agent using `pydantic-ai`'s `TestModel`.

## Non-goals

- Renaming `LLMClient`. It keeps the name even though it only embeds
  after the change (per scope decision).
- Replacing the embedding pipeline.
- Adding new product behavior. The HTTP contracts of `/describe` and
  `/extract-keywords` are unchanged.
- Touching `simulation_analysis_service`'s prompt, tool, or telemetry
  logic — only its model construction is reworked to use the shared
  helper.

## Design

### New module: `backend/src/mtg_helper/services/agents/`

```
services/agents/
├── __init__.py        # re-exports describe_turn(), extract_turn()
├── _model.py          # _make_google_model() shared helper
├── describe_agent.py  # DescribeDeps, agent, describe_turn()
└── extract_agent.py   # ExtractDeps, agent, extract_turn(), _KEYWORD_VOCAB
```

#### `_model.py`

```python
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from mtg_helper.config import settings


def make_google_model(model_name: str | None = None) -> GoogleModel:
    """Build a GoogleModel from settings. Lazy callers cache the result."""
    provider = GoogleProvider(api_key=settings.gemini_api_key)
    return GoogleModel(model_name or settings.chat_model, provider=provider)
```

#### `describe_agent.py`

- `DescribeDeps` dataclass: commander_name, commander_type,
  commander_oracle, commander_colors, partner_name, partner_oracle,
  bracket, at_history_limit (bool — triggers the "finalize now" hint).
- Module-level lazy `_AGENT: Agent[DescribeDeps, DescribeResponse] | None`
  with `Agent[DescribeDeps, DescribeResponse]` built by `_build_agent()`
  on first use. Same singleton pattern as
  `simulation_analysis_service._get_agent`.
- `@agent.system_prompt` decorated function rebuilds the static + dynamic
  parts of the current `_build_describe_system_prompt` from `ctx.deps`,
  including the strategy-tag vocabulary and the `_SANDBOX_RULES`.
  When `ctx.deps.at_history_limit` is true, appends the existing
  "force-finalize now" hint.
- `model_settings={"temperature": 0.3, "max_tokens": 2048}` (matches
  current `_LLM_TEMPERATURE` / `_LLM_MAX_COMPLETION_TOKENS`).
- Public driver `describe_turn(pool, commander_scryfall_id,
  partner_scryfall_id, bracket, history, message) -> DescribeResponse`:
  loads commander/partner from the DB (same as today), converts
  `history[-20:]` into `list[ModelMessage]`, builds `DescribeDeps`, runs
  `agent.run(user_message, deps=deps, message_history=...)`, returns
  `result.output`.

#### `extract_agent.py`

- Identical structure with `ExtractDeps` and
  `output_type=KeywordExtractResponse`.
- Move `_KEYWORD_VOCAB` here from `ai_service.py` (it's specific to this
  agent).
- Add a `@field_validator("archetype_tags", mode="after")` on
  `KeywordExtractResponse` (in `models/ai.py`) that silently filters
  unknown tags using `_KEYWORD_VOCAB` plus `tag_service._TRIBAL_SUBTYPES`
  derived `<subtype>_tribal` allow-list. Mirrors the current
  `_filter_known_keywords` behavior so the agent's API response stays
  vocabulary-clean even if the model emits a stray tag.

### History conversion

The frontend sends history as `[{role: "user"|"assistant", content: str}]`.
Convert each entry to `pydantic_ai.messages` parts:

- user → `ModelRequest(parts=[UserPromptPart(content=msg)])`
- assistant → `ModelResponse(parts=[TextPart(content=msg)])`

Trim to the last 20 entries. When `len(history) >= 20`, set
`deps.at_history_limit = True` so the system prompt adds the
finalize-now nudge (same as today).

### Modified files

#### `backend/src/mtg_helper/services/ai_service.py`

Delete: `describe_deck`, `extract_keywords`,
`_build_describe_system_prompt`, `_build_extract_system_prompt`,
`_find_done_json`, `_parse_describe_response`, `_parse_extract_response`,
`_filter_known_keywords`, `_call_llm`, `_JSON_DECODER`, `_KEYWORD_VOCAB`,
`_STRATEGY_TAGS`, `_SANDBOX_RULES`, `_BRACKET_DESCRIPTIONS`,
`_MAX_HISTORY_TURNS`, `_LLM_TEMPERATURE`, `_LLM_MAX_COMPLETION_TOKENS`,
and `LLMEmptyResponseError` (only used by the deleted helpers). `re` and
`json` imports go with them. `build_stage` and `suggest_cards` stay
untouched.

`_BRACKET_DESCRIPTIONS` and `_SANDBOX_RULES` are shared between the two
new agents — move them to `services/agents/_prompts.py` and import from
there.

#### `backend/src/mtg_helper/services/llm_client.py`

Delete `chat`, `chat_with_tools`, `ToolCall`, `ChatToolResponse`,
`asyncio`/`random` imports if no longer used by `embed()`. Keep `embed`,
its retry logic, and the class. Update the module docstring to say
"Gemini-backed embedding adapter".

#### `backend/src/mtg_helper/services/simulation_analysis_service.py`

Replace the inline `GoogleProvider` + `GoogleModel` construction in
`_build_agent` with `make_google_model()` from `services.agents._model`.
No other changes. The existing system prompt, tool, dataclass deps,
and timeout / usage-limit handling are unchanged.

#### `backend/src/mtg_helper/routers/ai.py`

Update imports: call `agents.describe_turn(...)` / `agents.extract_turn(...)`
instead of `ai_service.describe_deck` / `ai_service.extract_keywords`.
HTTP shape and rate limits unchanged.

#### `backend/src/mtg_helper/models/ai.py`

Add `@field_validator("archetype_tags", mode="after")` on
`KeywordExtractResponse` that filters via the allowed vocab (with a
lazy import of `_TRIBAL_SUBTYPES` to avoid the existing cycle).

### Tests

#### `backend/tests/conftest.py`

`make_mock_llm_client` drops the `chat = AsyncMock(...)` line — only
`embed` is mocked from here on.

#### `backend/tests/test_ai_service.py`

`_make_ai_client` drops the `chat` line too.

#### New: `backend/tests/test_agents.py`

Two happy-path tests using `pydantic_ai.models.test.TestModel` via
`agent.override(model=TestModel(custom_output_args=...))`:

- `test_describe_turn_returns_structured_output` — assert
  `DescribeResponse(done=True, description="...", ...)` flows through.
- `test_extract_turn_filters_unknown_tags` — feed an output with
  `archetype_tags=["voltron", "not_a_real_tag"]`, assert validator
  drops `"not_a_real_tag"`.

Tests don't need a real DB; the agent drivers will be exercised through
mocked `card_service` calls (commander lookup returns a stub).

## HTTP contract

Unchanged. `/api/v1/decks/describe` and `/api/v1/decks/extract-keywords`
return the same `DescribeResponse` / `KeywordExtractResponse` shapes.

## Risks

- **`pydantic-ai` output_type drift**: the SDK enforces the Pydantic
  schema via JSON-schema-mode generation. On rare cases the model
  fails the schema and the SDK retries (`retries=1` matches the sim
  agent). If retries are exhausted, the SDK raises — caller maps to a
  500. Acceptable: today the regex parser silently returns `done=False`
  on bad JSON, which is arguably worse (the conversation gets stuck).
- **History replay difference**: today, history is flattened into a
  single chat turn list with role tags. With pydantic-ai's
  `message_history`, the model sees discrete request/response turns.
  Behavior should be similar or better; verify via the test plan.
- **Migration coverage**: no existing tests cover `describe_deck` /
  `extract_keywords` end-to-end. New `TestModel`-backed tests give us
  the first coverage.

## Verification

1. `cd backend && uv run ruff check . && uv run ruff format .` — clean.
2. `uv run ty check src/` — clean.
3. `uv run pytest -q` — full suite green, including the two new tests.
4. Start the stack (`docker compose up`) and exercise the describe and
   extract flows from the frontend at `/decks/new`:
   - Send 3–4 messages; verify the agent asks one question at a time
     and eventually returns `done=True` with a description (or
     archetype tags) in the network response payload.
   - Confirm `reply` text is the conversational part only (no embedded
     JSON block leaks through).
5. Run a goldfish sim from `/decks/[id]/playtest` to confirm
   `simulation_analysis_service` still produces a structured analysis
   after the shared `make_google_model()` swap.

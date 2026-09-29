# MTG Assistant "I couldn't complete a verified answer" — Debug & Fix Handoff

## Session summary (short version)

- **Symptom:** First chat message with the MTG Assistant works; every follow-up message
  replies "I couldn't complete a verified answer. Please try the request again."
- **Root cause:** On follow-ups the model calls `inspect_deck_cards` (max 8 names) or
  `check_game_changers` (max 10 names) with too many names. The service raises a plain
  `ValueError` inside the tool body; pydantic-ai 1.71 re-raises it and aborts the whole
  agent run; `run_assistant` swallows the exception into that generic fallback text.
- **Reproduced:** two-turn repro script against the real agent in the running backend
  container crashes on turn 2 with `ValueError: inspect_deck_cards accepts at most 8 names`.
- **Fix applied (repo HEAD `backend/src/mtg_helper/services/mtg_assistant.py`):**
  - `inspect_deck_cards` now takes `names: Annotated[list[str], Field(max_length=8)]`
    and raises `ModelRetry` instead of letting the ValueError kill the run.
  - `check_game_changers` now takes `names: Annotated[list[str], Field(max_length=10)]`
    and raises `ModelRetry` likewise.
  - Schema caps advertise maxItems to the model and make oversized calls a retryable
    validation error; `ModelRetry` is the second line of defense inside the tool body.
- **Tests:** new `backend/tests/test_mtg_assistant_tool_bounds.py` (4 no_db tests) —
  over-limit calls raise `ModelRetry` and never reach the service. Related suites pass
  (23 passed). Ruff clean.
- **Recorded follow-up:** the steps below report the Docker rebuild and successful
  two-turn reproduction as completed. Those live checks were not repeated during the
  2026-09-06 documentation review.

---

Status: **fix applied; Docker rebuild and live reproduction recorded as complete below**.
On 2026-09-06, the tool-bound regression and assistant quality evaluation test files were
run locally: **8 passed**. This confirms those tests, not the current deployed image.

## User-reported symptom

In the deck coach chat ("MTG Assistant"), the **first message** in a conversation works,
but **every follow-up message** returns:

> I couldn't complete a verified answer. Please try the request again.

That string is the **generic exception fallback** in `run_assistant`:
`backend/src/mtg_helper/services/mtg_assistant.py` (repo HEAD ≈ line 440–449), i.e. *any*
unexpected exception raised inside `Agent.run(...)` gets swallowed and replaced by this
reply. So the real defect is an exception thrown during follow-up agent runs.

## Evidence gathered

- Workspace: `C:\Users\mario\sources\mtg_helper` (git HEAD `fe5d7707`; uncommitted WIP in
  `mana_base_service.py` + tests that is unrelated — do not revert).
- Running docker stack: `mtg_helper-backend-1` etc. Backend container runs a **stale baked
  image** (created 2026-08-23) with **no source mounts**, so container code ≠ repo HEAD
  (container: `_MAX_TOOL_CALLS=6`, `_REQUEST_LIMIT=8`, 64k input, 45s timeout; repo HEAD:
  10/12/128k/120s and extra tools `check_game_changers`, `collection_only`).
- Local dev DB (`mtg_helper-postgres-1`, db `mtg_helper`) has the card catalog
  (~31.9k cards) but **no accounts/decks** — the user's real deck is not in this DB.
- Reproduced the failure **in-container** with `.local/repro_assistant.py` (copied to
  `/tmp/repro_assistant.py`): turn 1 (no history) succeeds; turn 2 (with history) crashes
  inside pydantic-ai with:
  `ValueError: inspect_deck_cards accepts at most 8 names`.
- Traceback shows pydantic-ai 1.71.0 propagates **exceptions raised inside a tool body**
  out of `Agent.run()` (unlike `ModelRetry`, which becomes a retry prompt to the model).
  → `run_assistant` catch-all returns the fallback message the user sees.
- Probing pydantic-ai in-container (`/tmp/probe2.py`) confirmed: an **oversized list arg**
  rejected at *argument validation* (schema `maxItems`) is retried and the run completes;
  a tool **body ValueError** kills the run.
- Tool JSON schema for `inspect_deck_cards` had NO `maxItems` bound, so the model could
  pass >8 names; the service guard then raised inside the tool body.
- `OPENAI_API_KEY` + model `gpt-5.6-luna` work from the container (checked `/models` and a
  live chat call, `.local/check_openai.py`).

## Root cause (confirmed)

On follow-up turns the LLM calls `inspect_deck_cards` (limit 8 names) — and can call
`check_game_changers` (limit 10 names) — with **more names than allowed**. The underlying
service raises a plain `ValueError` **inside the tool body**; pydantic-ai 1.71 re-raises
tool execution exceptions, aborting the whole agent run; `run_assistant` converts that to
the generic fallback. First turn works because the model does not yet over-request.

## Fix (applied and verified)

Repo HEAD: `backend/src/mtg_helper/services/mtg_assistant.py`

1. ✅ Done — `inspect_deck_cards` tool:
   - import `Annotated` (typing) and `ModelRetry` (pydantic_ai) — added at top.
   - signature: `names: Annotated[list[str], Field(max_length=8)]`
     → pydantic-ai arg validation rejects >8 as a retryable error (run survives).
   - body guard: `if len(names) > 8: raise ModelRetry(...)` as belt-and-braces.
2. ✅ Done — `check_game_changers` tool (same pattern, `max_length=10`, `ModelRetry` guard).
3. ✅ Done — regression tests `backend/tests/test_mtg_assistant_tool_bounds.py` (4 no_db
   tests): over-limit calls raise `ModelRetry` and never reach the service layer.
   Existing tests pinning `ValueError` at the *service* layer stay valid.
4. ✅ Done — rebuilt backend image from current source and restarted the stack.
   **Note:** this repo's live stack runs from `docker-compose.prod.yml` (host data under
   `/srv/mtg-helper/data`, no host port 5432). Recreate with:
   ```
   docker compose -f docker-compose.prod.yml up -d --build backend postgres qdrant
   ```
   (Running plain `docker compose up` uses the dev file and conflicts on port 5432.)
5. ✅ Done — in-container two-turn repro re-run on the fixed backend: turn 2 now completes
   (`mode=replacement`, no traceback, 0 errors in log).
6. ✅ Done — backend checks: `uv run ruff check .` clean; affected no_db pytest suites:
   47 passed (tool-bounds + agent contracts + deck context + assistant tools + coach pipeline).
   DB-backed tests (marked db) require `TEST_DATABASE_URL` and were not run locally.

## Useful artifacts

- `.local/repro_assistant.py` — two-turn repro (real agent, real OpenAI, DB-built deck).
- `.local/check_openai.py` — API/model reachability check.
- `.local/backend.log` — backend container logs (startup only; container restarted a lot).
- `/tmp/probe_tool_errors.py`, `/tmp/probe2.py` (in container) — pydantic-ai behavior probes.
- Deck the user is testing with: https://moxfield.com/decks/leSeAe3HM3yzMusDvNs7UA

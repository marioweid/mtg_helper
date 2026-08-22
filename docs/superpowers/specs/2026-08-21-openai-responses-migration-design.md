# OpenAI Responses Migration — Design

**Critic round:** 2

## Goal

Remove Gemini from production AI workflows and use Pydantic AI's OpenAI Responses API with fixed
`gpt-5.6-luna`, one `OPENAI_API_KEY`, bounded usage, and safe usage logging. Preserve Google OAuth
and the existing chat, deck-doctor, and targeted-replacement API/frontend contracts.

## Decision and approach

The unified `mtg_assistant` owns all Commander Coach AI behavior. Production already reaches it
through `commander_coach.orchestrator.run_coach`; restoring the old router-and-specialist pipeline
would recreate a second assistant architecture and multiple billing surfaces.

`run_coach` remains the thin production entry point and delegates one bounded run to
`run_assistant`. Deterministic memory handling stays in the API before that call. Deterministic
tools used by the unified assistant remain in place. The unreachable AI router and specialist
agents are removed outright, with no aliases or dual path.

All other production AI workflows continue to use the shared `OpenAIResponsesModel` factory and
their current workflow-specific settings and failure policies.

## Production ownership and active AI run sites

There are six production `Agent.run` sites after cleanup, not twelve:

1. `commander_suggestor_agent.suggest_turn` — commander discovery.
2. `describe_agent.describe_turn` — deck-description conversation.
3. `extract_agent.extract_turn` — structured deck-direction extraction.
4. `deck_doctor_agent.doctor_deck` — the separate `/doctor` endpoint.
5. `mtg_assistant.run_assistant` — Commander Coach chat, doctor, and replacement behavior via
   `run_coach`.
6. `simulation_analysis_service.analyze_simulation` — playtest analysis.

Each site must construct fixed Luna through `make_openai_model()`, pass explicit `UsageLimits`, and
call `log_run_usage()` exactly once after a successful run. Prompts, outputs, exceptions, API keys,
and user content are never logged.

## Response mapping

`AssistantAnswer` carries enough typed replacement intent to map without reintroducing a specialist:
the target card name, optional keep reason, and each recommendation's role match and optional
tradeoff. Existing recommendation ids and cut names remain the grounding keys.

`mtg_assistant._to_response` maps by requested output mode:

- `chat`: return `mode="chat"` with both `doctor` and `replacement` unset.
- `doctor`: retain only cuts present in the deck and recommendations returned by a deterministic
  tool, then populate `doctor`; if no grounded action remains, return chat rather than an empty
  doctor response.
- `replacement`: validate the target against the current deck, retain only tool-grounded
  recommendations, and populate `TargetedReplacementResponse` under `replacement`. Its summary is
  the assistant reply, `best_pick` is the first grounded option when present, and
  `tool_call_count` comes from the unified run. `doctor` is unset. A valid keep recommendation may
  have no options; a missing or invalid target downgrades to a non-actionable chat response.

This keeps `CommanderCoachResponse` and `frontend/lib/types.ts` semantics unchanged: the frontend
continues to render replacement UI from `result.replacement`, never from `result.doctor`.

## What changes

- Keep `commander_coach/orchestrator.py` as the one Coach production entry point; make API and tests
  call that entry point rather than dead router/specialist functions.
- Change `mtg_assistant.py` only as needed for the typed replacement fields and the explicit
  chat/doctor/replacement mapping above.
- Remove `commander_coach/router_agent.py` and the superseded `specialists` package: `identity.py`,
  `cuts.py`, `upgrades.py`, `challenger.py`, `replacement.py`, the deck-doctor alias, and exports.
- Do not remove deterministic analysis used by the unified assistant, including
  `mtg_assistant_tools.py`, `pipeline.py`, mana/curve/fit services, and card-search services. Do not
  fold unrelated deterministic-helper cleanup into this migration.
- Narrow model/run-contract tests to the six production run sites and remove tests whose only
  purpose is invoking deleted specialist agents.
- Replace stale router/specialist patches in Coach tests with unified-assistant overrides.
- Keep OpenAI configuration/dependency/env/Compose changes and remove Gemini counterparts while
  retaining `google-auth` and `GOOGLE_OAUTH_CLIENT_ID`.

## Tests

- A production-path `run_coach` behavioral test drives the unified agent in replacement mode with a
  deterministic model and mocked card-search boundary. It asserts `mode="replacement"`,
  `replacement` is populated with the validated target and grounded best pick/options, and
  `doctor is None`.
- Existing `run_coach` chat/doctor grounding tests remain behavior tests of the same production
  path. Add focused mapping cases for invalid targets and ungrounded recommendations.
- The Coach endpoint replacement test overrides `mtg_assistant`, not a deleted specialist, and
  verifies serialized data matches the frontend contract.
- `test_agent_run_contracts.py` contains exactly the six active sites and verifies limits, one
  success usage log, no success log on failure, and each site's established fatal/fallback policy.
- `test_openai_model_config.py` contains exactly those six builders and verifies fixed Luna,
  Responses API settings, `openai_store=False`, and low verbosity.
- Remove specialist-only tests; retain deterministic service tests that do not call a deleted AI
  agent.
- Run focused tests first, then Ruff, formatting check, `ty check src/`, and the backend suite with
  model requests disabled. Any stale import or warning is a failure.

## Migration docs and configuration

- `backend/pyproject.toml` and `uv.lock`: OpenAI Pydantic AI extra only; no Gemini provider
  dependency. `google-auth` remains for sign-in.
- `backend/src/mtg_helper/config.py`, safe env examples, and Compose: require only
  `OPENAI_API_KEY` for AI. Do not print, copy, or inspect real secret files.
- README/current operations text: OpenAI Responses is the sole AI provider and billing surface.
- `docs/superpowers/specs/2026-07-12-generic-hub-card-search-design.md`: mark Gemini model-default
  text as a historical implementation record superseded by this migration; do not rewrite its
  still-valid card-search design as though OpenAI was used at that time.

## Shared boundary

`make_openai_model()` creates fixed Luna through `OpenAIResponsesModel` and `OpenAIProvider`.
`openai_model_settings()` supplies privacy, verbosity, token, and reasoning settings.
`log_run_usage(workflow, operation, RunUsage)` records counters only and cannot fail a successful
workflow. Old Google helpers are deleted, not retained as aliases.

## Kept simple / not doing

No provider abstraction, model routing, configurable tiers, pricing store, migration flag,
compatibility shim, or specialist fallback architecture. No design pattern is needed: one unified
Coach owner plus three small shared functions removes the actual duplication.

Frontend types and components do not change because the fix restores their existing contract.
Deterministic modules outside the deleted agent path are not broadly reorganized in this migration.

## Error handling

- Missing OpenAI configuration, model construction failure, dependency/lock inconsistency, stale
  imports, and schema/type/test failures are fatal: fail loudly with context.
- Each production AI run keeps its current fatal-versus-fallback policy. The unified Coach treats
  timeout, usage-limit, tool, and model failures as tolerable request failures and returns its safe
  chat fallback; other workflows do not gain new fallback behavior.
- Invalid or ungrounded model recommendations are tolerable but never silently promoted to action:
  filter them, downgrade an invalid replacement/empty doctor result to chat, and cover that behavior
  in tests.
- Usage logging failure is tolerable: report a context-only telemetry error and preserve the
  successful response.
- The test suite is a batch operation: one failing test does not hide later failures, but any failure
  makes migration verification fail.

## Open questions

None. The existing production path and response/frontend models resolve ownership and mapping
without a new product decision.

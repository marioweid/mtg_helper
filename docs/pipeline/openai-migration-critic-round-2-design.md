# OpenAI Migration Critic Round 2 — Design

## Goal

Revise the migration so Commander Coach has one production AI owner and still returns valid chat,
doctor, and replacement payloads.

## Approach

Keep `orchestrator.run_coach` as the thin production entry point and the unified `mtg_assistant` as
the sole Coach agent. Delete the unreachable router/specialist agent path, correct unified response
mapping, and test only the six production `Agent.run` sites.

## What changes

- Map replacement output into `CommanderCoachResponse.replacement`, never `doctor`.
- Remove the dead Coach router and specialist agent package and their agent-only tests.
- Retain deterministic tools and services used by the unified assistant; avoid unrelated cleanup.
- Update run-site contracts to six and mark historical Gemini-default documentation superseded.

## Shared boundary

Production AI sites use fixed Luna through `make_openai_model()`, explicit per-workflow
`UsageLimits`, and counter-only `log_run_usage()`.

## Kept simple / not doing

No second Coach pipeline, compatibility path, provider layer, frontend redesign, or broad helper
refactor. No design pattern is needed; direct delegation is the smallest coherent ownership model.

## Error handling

Configuration, dependency, import, type, and test failures are fatal. Unified Coach runtime failures
remain safe chat fallbacks. Invalid model actions are filtered and reported as non-actionable chat;
usage-log failures preserve successful responses.

## Open questions

None.

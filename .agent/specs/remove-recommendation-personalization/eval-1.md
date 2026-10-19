# Evaluation — round 1

**Overall: FAIL.** Two failed verification deliverables, seven UNVERIFIED criteria
(which count as failures), and the scope findings below. Offline green tests do not establish
database retention, personalization independence, or working browser workflows.

- Repository: `C:\Users\mario\sources\mtg_helper`, branch `mw/db_migration`.
- Fixed base: `8683c80f242e6b05ceefa1c35b346a18d8342be0`.
- Read every acceptance verification method and `VERIFY.md` before testing.
- Existing unrelated working-tree modifications were present before evaluation; preserved.
- Commands below run from `backend/` or `frontend/` as appropriate. Artifact paths are
  relative to this spec directory. Full captured output is in `artifacts/`.
- Bare `pnpm` is unavailable; used the installed pinned package manager through Corepack.

## Boot and gate feedback

Command: `docker compose up -d --wait postgres`

```text
unable to get image 'postgres:16': failed to connect to the docker API at npipe:////./pipe/docker_engine; check if the path is correct and if the daemon is running: open //./pipe/docker_engine: The system cannot find the file specified.
```

Command: `docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_retired_personalization_api.py tests/test_recommendation_personalization_removal.py tests/test_new_cards_personalization_removal.py tests/test_personalization_data_retention.py`

```text
failed to connect to the docker API at npipe:////./pipe/docker_engine; check if the path is correct and if the daemon is running: open //./pipe/docker_engine: The system cannot find the file specified.
```

Command: `curl.exe --max-time 5 -sS http://localhost:8000/health`

```text
curl: (7) Failed to connect to localhost:8000 after 2248 ms: Could not connect to server
```

Evidence: `artifacts/eval-db-start.log`, `eval-isolated-tests.log`, `eval-health.log`.
No app/container could be started using the authorized isolated procedure. No live mode,
environment edits, DSN substitution, live database connection, or live writes were attempted.
VERIFY names no boot-log files; captured boot logs in this spec's artifacts instead.

Parent `gate-1.md` reports backend safety tests/Ruff/format/ty and frontend
lint/typecheck/106 tests/build green, but the isolated database gate failed for this same
Docker pipe. **The overall gate remains FAIL**, not waived by the offline checks.

## Acceptance results

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 | UNVERIFIED | `corepack pnpm exec vitest run app/decks/coach-personalization.test.tsx app/preferences/page.test.tsx --reporter=verbose` → `2 passed`, including `does not expose persistent Assistant-memory client requests`. The Assistant test only checks two client properties, not page loading, requests, controls, or answering. Browser command `playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/not-a-uuid/coach` → `Error: net::ERR_CONNECTION_REFUSED at http://localhost:3000/decks/not-a-uuid/coach`. Valid isolated deck/answer check blocked by boot failure. Screenshot and console saved, but they do not show a working Assistant. |
| AC2 | UNVERIFIED | `uv run pytest -q -W error tests/test_assistant_personalization_removal.py tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py` → `31 passed in 0.19s`. Edge command `uv run pytest -q -W error tests/test_assistant_sessions.py::test_unauthorized_deck_and_invalid_conversation_never_create_turn tests/test_commander_coach_pipeline.py::test_coach_request_rejects_invalid_history -vv` → `5 passed in 0.12s`, including empty-message, empty-history, unknown-role, too-many-turns. Existing real TestModel orchestration/tracing coverage passes, but the new removal test replaces `run_assistant` with AsyncMock; it never captures provider history, exercises remember/forget, background progress/failure, or the separate doctor path with saved rows. Those required behaviors remain unexercised. |
| AC3 | FAIL | Exact verify selection `uv run pytest -q -W error tests/test_retired_personalization_api.py -k memory` → `2 deselected in 0.01s`; exit `5`. No test name matches memory. Edge command `uv run python ../.agent/specs/remove-recommendation-personalization/artifacts/eval-http-probes.py` → `GET /api/v1/decks/not-a-uuid/coach/memory -> 404 {"detail":"Not Found"}` and `PUT /api/v1/decks/not-a-uuid/coach/memory -> 404 {"detail":"Not Found"}`; OpenAPI `response_fields=["doctor", "mode", "recommendations", "replacement", "reply"]`. This is real ASGI routing, without lifespan/DB; authenticated valid-deck HTTP and actual Assistant response-body checks remain blocked/missing. |
| AC4 | UNVERIFIED | Focused page command in AC1 → `renders the Preferences empty state without personalization controls` passed. `playwright-cli -s=remove-recommendation-personalization open http://localhost:3000/preferences` → `Error: net::ERR_CONNECTION_REFUSED at http://localhost:3000/preferences`. `playwright-cli -s=remove-recommendation-personalization console` → `Total messages: 0 (Errors: 0, Warnings: 0)`. Screenshot inspected: browser connection-error page, not Preferences. The static markup test checks copy/three absent labels, not navigation, all forms/toggles, or lifecycle network calls. Unauthenticated/navigation edge cannot be exercised against unavailable app. |
| AC5 | UNVERIFIED | `uv run pytest -q -W error tests/test_retired_personalization_api.py` → `2 passed in 0.09s`. These issue unauthenticated requests with all-zero nonexistent IDs, not authenticated valid fixtures, and do not exercise retained account GET/PATCH or collection access. HTTP edge probe command in AC3 → `DELETE /api/v1/me/preferences/not-a-uuid -> 404 {"detail":"Not Found"}`, `DELETE /api/v1/decks/not-a-uuid/feedback/not-a-uuid -> 404 {"detail":"Not Found"}`, `GET /api/v1/me/ranking-weights -> 404 {"detail":"Not Found"}`, and retained route `POST /api/v1/decks/not-a-uuid/coach -> 401 {"detail":"missing bearer token"}`. Valid ownership/account/collection checks blocked by isolated boot failure. |
| AC6 | UNVERIFIED | `uv run pytest -q -W error tests/test_recommendation_personalization_removal.py` → `2 passed in 0.02s`. Tests inspect source/signatures and collect SQL with a fake connection returning no cards. No real Builder/free-form/mana/swap results, ordered identities, deck-fit protection, seeded tastes/weights/feedback/history, or New Cards results are compared. Required extreme-weight/avoid-all and cross-deck edge matrix cannot run: isolated test command above → `open //./pipe/docker_engine: The system cannot find the file specified.` |
| AC7 | UNVERIFIED | `uv run pytest -q -W error tests/test_new_cards_personalization_removal.py` → `1 passed in 0.02s`. It only searches `_context`/`_candidates` source text. No captured deterministic assessment, old-context cache row, retained historical row, or changed-row fingerprint/result check. Old-context-with-empty-notes/preferences and reanalysis edge unexercised: isolated test command above → `open //./pipe/docker_engine: The system cannot find the file specified.` There is additional DB coverage in `test_new_cards_pilot.py`, but it too requires the unavailable DB and does not replace the specified missing historical-cache check. |
| AC8 | FAIL | `corepack pnpm test -- app/decks/coach-personalization.test.tsx app/preferences/page.test.tsx components/personalization-removal.test.tsx components/card-workspace.test.tsx components/discover-state.test.ts components/new-cards-panel.test.tsx lib/coach-conversation.test.ts` → `Test Files 21 passed (21)`, `Tests 106 passed (106)` (this invocation ran all tests). `Test-Path components/personalization-removal.test.tsx` → `False`. Direct selection `corepack pnpm exec vitest run components/personalization-removal.test.tsx` → `No test files found, exiting with code 1`; exit `1`. Required deliverable absent: no Builder Reject/replacement/exclusion/remount or no-pet/no-retired-network page-action coverage. Edge command `corepack pnpm exec vitest run components/new-cards-panel.test.tsx components/discover-state.test.ts lib/coach-conversation.test.ts --reporter=verbose` → `40 passed`; includes `retains undo on a failed undo request` and irregular/bounded history. Those retained subchecks are useful, but do not exercise Builder navigation or browser workflows. |
| AC9 | UNVERIFIED | `uv run pytest -q -W error tests/test_personalization_data_retention.py` → `1 passed in 0.02s`. This test is marked `no_db` and only finds four `CREATE TABLE IF NOT EXISTS` strings. It neither seeds/snapshots actual rows nor applies schema once/twice, checks unrelated records, or observes repeated requests for legacy table reads/writes. Required second-apply/repeated-request edge blocked: isolated test command above → `open //./pipe/docker_engine: The system cannot find the file specified.` No `psql` row evidence exists; no retention pass claimed. |

## Browser evidence

Before opening the browser, set `PLAYWRIGHT_MCP_OUTPUT_DIR` to the absolute path of
`.agent/specs/remove-recommendation-personalization/artifacts/`.

- Preferences: `artifacts/eval-preferences.png`, `eval-browser-open.log`,
  `eval-browser-console.log`.
- Assistant malformed-deck edge: `artifacts/eval-assistant-unavailable.png`,
  `eval-assistant-browser.log`, `eval-assistant-console.log`.
- Personally opened both screenshots. Preferences shows `This site can’t be reached` /
  `ERR_CONNECTION_REFUSED`; the later Assistant capture is blank. Neither is UI acceptance evidence.
- Real isolated UI happy paths and additional navigation interactions are blocked, not passed.

## Builder feedback / required next checks

1. Restore Docker Desktop's Linux-container daemon; rerun the isolated procedure only.
   Do not substitute live data. Run DB acceptance even if offline tests pass.
2. AC1: replace the client-shape-only test (`frontend/app/decks/coach-personalization.test.tsx:1-8`)
   with actual Assistant page/action coverage: load a fixture deck, record all requests,
   send/receive a deterministic streamed answer, assert no memory UI/requests; test load/error edge.
3. AC2: replace the business-logic mock at
   `backend/tests/test_assistant_personalization_removal.py:44-45` with a deterministic
   provider seam. Capture the actual prompt/history, verify remember/forget are ordinary chat,
   saved-note sentinels never arrive, account context and progress remain, sync/background
   failure paths work, and the separate doctor route is covered.
4. AC3/5: provide a memory-named test so `-k memory` runs. Use authenticated seeded account/deck
   IDs for the full retired method matrix, assert actual Assistant JSON, and prove account
   GET/PATCH/collections still work. Keep malformed-ID/unauthenticated probes as extra cases.
5. AC6: source-string inspection is not behavioral independence. Seed the specified legacy
   records, compare ordered public results before/after with identical deck/source state across
   every named retrieval lane, deck fit, New Cards and Discover. Include extreme settings,
   canonical printings, explicit constraints, and structural-protection edge cases.
6. AC7: replace source inspection with captured-provider context/cache tests. Add a real
   personalized old cache row (including empty old settings), assert it is not current, then
   check historical retention and changed legacy rows do not change fresh fingerprints/results.
   Specifically examine `services/new_cards/service.py:99-106`: publication uses an upsert
   that overwrites the single old assessment for the same deck/account/oracle. Establish
   whether reanalysis would lose the historical advice required by AC7; not runtime-verified here.
7. AC8: add the missing `components/personalization-removal.test.tsx`; drive actual deck/Builder
   handlers and a fresh navigation session, assert replacement/exclusion, no retired requests,
   no pet indicators, filters/planned additions, and Discover Report incorrect. Existing retained
   New Cards/history tests do not cover the absent Builder checks. Use `pnpm exec vitest run`
   for unambiguous focused selection; the spec's `pnpm test --` invocation ran the whole suite.
8. AC9: replace/augment the source-text test with real disposable-Postgres snapshots of all
   named tables, schema applied twice, unrelated data equality, and repeated-request access
   observation. Prove a relevant behavioral test fails under a plausible mutation.

## Scope

Reviewed `git diff 8683c80f242e6b05ceefa1c35b346a18d8342be0...HEAD`, excluding
`build-notes.md` until after writing verdicts. Captured non-notes diff:
`artifacts/eval-scope.diff`. Effective fixed weights match the old `RankingWeights` defaults
(synergy 0.25 + 0.22, popularity 0.10, source terms 0.20 each, quota 1.0); the apparent
constant changes alone are not a retuning finding.

| Finding | Type | Evidence |
|---|---|---|
| S1 | VIOLATES | `docker-compose.prod.yml:25-58,105-108`: fixed-base diff removes the production Postgres service/health dependency, changes backend DATABASE_URL to required `MTG_DATABASE_URL`, and adds required external `shared_database` network. Non-goal: do not commit unrelated work, including live-database development changes (spec:20); no personalization criterion requires production database migration. `git log --oneline BASE..HEAD` includes `c1b7e272 migrated to shared db` and `02639497 added missing network` before `234d0696 spec(remove-recommendation-personalization): round 1`. These predate the feature commit; isolate scope/resolve the requested base with the owner, do not discard or automatically revert unrelated work. |
| S2 | VIOLATES | `backend/tests/test_assistant_personalization_removal.py:44-45`: `run = AsyncMock(return_value=expected)` followed by `monkeypatch.setattr(assistant_service, "run_assistant", run)` replaces Assistant business execution, rather than the external provider/storage seam. Breaks spec:177-179 (behavioral checks, not business-logic mocks) and AC2's captured deterministic-adapter verification. This test cannot prove what reaches the model. |

## Cleanup and self-violation check

- No app or container successfully started. In-process test apps exited with their processes.
- `playwright-cli -s=remove-recommendation-personalization close` →
  `Browser 'remove-recommendation-personalization' closed` (`artifacts/eval-browser-close.log`).
- `docker compose down` → `open //./pipe/docker_engine: The system cannot find the file specified.`
  (`artifacts/eval-stop.log`). No reachable daemon/containers to stop; no volumes deleted.
- `git status --porcelain` captured in `artifacts/eval-final-status.log`. All outside-slug
  modified/untracked paths match the initial status (AGENTS/README/config/main/conftest/base
  compose and the existing live-development files/spec). No evaluator-created changed path
  outside this spec directory appears in git status; no such path was reverted/deleted.
  Ignored tool caches may have been updated by the requested test runs; no source/env edits.

## Build-notes comparison

Read `build-notes.md` only after the verdicts and scope table above were written.
Its offline-test counts and Docker/browser limitations are consistent with the observed
106 frontend tests and missing Docker pipe. Its descriptions of the two frontend tests
are accurate but much narrower than AC1/AC4. The claimed added “removal/data-retention
coverage” (line 24) is not the specified behavioral/database retention verification:
the new recommendation, New Cards and retention files primarily inspect source strings.
The claimed client-property mutation proof (lines 43-44) tests API object shape, not
Assistant loading/answering or legacy database independence. I did not independently
repeat that claimed mutation. The notes do not account for the unrelated production
database migration included by the fixed base, or the absent AC8 test deliverable.

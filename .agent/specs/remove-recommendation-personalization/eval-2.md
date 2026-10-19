# Evaluation — round 2

**Overall: FAIL.** Five criteria passed, AC3 failed, and AC1/AC6/AC8 remain
UNVERIFIED (which counts as failure). Scope also has unmet constraints.

Repository: `C:\Users\mario\sources\mtg_helper`, branch `mw/db_migration`.
Fixed change under test: `git diff 8683c80f242e6b05ceefa1c35b346a18d8342be0...HEAD`;
HEAD was `2fbd94e3`. Existing unrelated dirty paths were recorded before testing
and preserved. No environment files, application DSNs, or production data were changed.

## Environment and executed commands

Read `spec.md` (including every verify method) and `VERIFY.md` first. Initially:

```text
docker compose up -d --wait postgres
unable to get image 'postgres:16': failed to connect to the docker API at npipe:////./pipe/docker_engine
```

The daemon became available during evaluation. A later explicit retry succeeded:

```text
docker compose up -d --wait postgres
Container mtg_helper-postgres-1 Healthy
EXIT=0
docker compose exec -T postgres psql -U mtg -d postgres -Atc "SELECT datname FROM pg_database WHERE datname = 'mtg_helper_test'"
mtg_helper_test
```

All database tests then used VERIFY's base Compose backend, fixed local `_test`
database, and `OPENAI_API_KEY=test`. No live override, live startup, or paid model
requests. Initial Docker failures are retained in artifacts, but **are not the final
database verdict**.

Commands below are exact; backend host commands ran from `backend/`, frontend
commands from `frontend/`, Compose/browser commands from the repository root.
`pnpm` was not directly on PATH; its installed Corepack launcher worked.

**B — named backend acceptance suite:**

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_assistant_personalization_removal.py tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py tests/test_retired_personalization_api.py tests/test_recommendation_personalization_removal.py tests/test_new_cards_personalization_removal.py tests/test_personalization_data_retention.py
FAILED tests/test_retired_personalization_api.py::test_memory_routes_are_absent_for_an_authenticated_owned_deck
TypeError: AsyncClient.get() got an unexpected keyword argument 'json'
1 failed, 38 passed in 7.39s
EXIT=1
```

**F — named frontend acceptance suites:**

```text
corepack pnpm test -- app/decks/coach-personalization.test.tsx app/preferences/page.test.tsx components/personalization-removal.test.tsx components/card-workspace.test.tsx components/discover-state.test.ts components/new-cards-panel.test.tsx lib/coach-conversation.test.ts
Test Files 22 passed (22)
Tests 108 passed (108)
EXIT=0
```

This invocation actually ran all 22 files, not only the supplied filenames; each
named file appears in `artifacts/eval-2-frontend-tests.log`. Passing this suite does
not establish behavior its tests never exercise.

**O — offline backend tests:**

```text
uv run pytest -q -W error -m no_db tests/test_assistant_personalization_removal.py tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py tests/test_recommendation_personalization_removal.py
34 passed in 0.21s
EXIT=0
uv run pytest -q -W error -m no_db tests/test_retrieval_service.py tests/test_deck_fit_service.py
12 passed, 111 deselected in 0.06s
EXIT=0
```

**H — additional real in-process FastAPI HTTP probe:**

```text
uv run python ../.agent/specs/remove-recommendation-personalization/artifacts/eval-2-http-probe.py
GET /openapi.json 200
retired_paths=[]; retired_models=[]
retained_discover_report_paths=['/api/v1/decks/{deck_id}/recommendations/runs/{run_id}/feedback']
request_fields=['conversation_id', 'history', 'message', 'mode']
response_fields=['doctor', 'mode', 'recommendations', 'replacement', 'reply']
response_modes=['doctor', 'builder', 'mana', 'meta', 'chat', 'replacement']
unauthenticated GET /api/v1/decks/00000000-0000-4000-8000-000000000001/coach/memory 404 {"detail":"Not Found"}
unauthenticated PUT /api/v1/decks/00000000-0000-4000-8000-000000000001/coach/memory 404 {"detail":"Not Found"}
unauthenticated GET /api/v1/decks/not-a-uuid/coach/memory 404 {"detail":"Not Found"}
unauthenticated GET /api/v1/me 401 {"detail":"missing bearer token"}
AC3 verify test line 32 GET invocation: TypeError: AsyncClient.get() got an unexpected keyword argument 'json'
```

H also exercised every retired preferences/weights/legacy-feedback verb with both a
UUID and `not-a-uuid`; all returned `404 {"detail":"Not Found"}`. Full exact output
is `artifacts/eval-2-http-probe.log`. It uses the real app with lifespan disabled,
no authentication overrides and no database access. Its UUID is not claimed to be
an owned fixture deck.

## Acceptance

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 | UNVERIFIED | F: `app/decks/coach-personalization.test.tsx (1 test)` passed, but that file only checks two missing client properties; it never renders the Assistant, loads a deck, or displays an answer. `playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/coach` followed by `snapshot` produced `paragraph: sign in required`. Screenshot `artifacts/eval-2-assistant-final.png` inspected; console `artifacts/eval-2-assistant-final-console.txt` captured. Edge: unauthenticated deck navigation was exercised, not bypassed. No authenticated isolated-stack normal-answer UI flow was verified. |
| AC2 | PASS | B and O passed the Assistant/provider, session, history, doctor, grounding, invalid-history, unauthorized-deck and parallel-account/session checks. Supplemental command `uv run python ../.agent/specs/remove-recommendation-personalization/artifacts/eval-2-background-probe.py` produced `sync POST /coach 200 {"data":{"mode":"chat","reply":"Answer","recommendations":[],"doctor":null,"replacement":null},"meta":null}`, `background POST /coach/start 200`, `GET /coach/job/stream 200`, progress events `assistant_routing`, `assistant_routed`, `assistant_thinking`, `assistant_grounding`, and `event: done`. Output: `turns=2; same_session=True; distinct_traces=True` and `CAPTURED_CHAT_HISTORY=True; ORDINARY_FORGET_COMMAND=True; NO_MEMORY_FIELDS=True`. Edge: deterministic provider failure returned `provider_failure SSE 200 {"mode": "chat", "reply": "I couldn't complete a verified answer. Please try the request again.", "recommendations": [], "doctor": null, "replacement": null}`. This probe uses the existing test fixture's auth/deck-storage seam and real orchestration/tracing/SSE, not a mocked Assistant service. |
| AC3 | FAIL | B actually failed at `backend/tests/test_retired_personalization_api.py:32`: `TypeError: AsyncClient.get() got an unexpected keyword argument 'json'`. Thus the required authenticated valid-deck memory-route test never performs its GET or subsequent response assertion. H independently reproduced that exception and verified public OpenAPI omits memory fields/models/mode. Edge: H's unauthenticated and malformed-deck GET/PUT paths returned `404 {"detail":"Not Found"}`; supplemental AC2 responses omitted memory fields. These partial successes do not make the required failing verification pass. |
| AC4 | PASS | F: `app/preferences/page.test.tsx (1 test)` passed. Opened with `PLAYWRIGHT_MCP_OUTPUT_DIR` set to this spec's artifacts directory: `playwright-cli -s=remove-recommendation-personalization open http://localhost:3000/preferences`. `eval` returned `{"heading":"Preferences","preferencesLink":true,"controls":0,"copy":"Preferences\n\nNothing in here yet.\n\nProfile settings may come in the future."}` (exact runnable expression in `artifacts/eval-2-preferences-dom.txt`). `requests` contained only `POST /__nextjs_original-stack-frames => [200] OK` among nonstatic requests, not retired APIs. Screenshots `eval-2-preferences.png` and `eval-2-preferences-mobile.png` inspected; both exact empty-state paragraphs and heading rendered. Edge: `resize 375 812` then `reload` retained the empty state and no settings controls/retired requests. Console files captured for both sizes; they report environment `MissingSecret` and a favicon 404, not a personalization request. This proves the static page, not successful OAuth. |
| AC5 | PASS | `docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_retired_personalization_api.py -k 'not memory'` → `2 passed, 1 deselected in 2.46s`, `EXIT=0`. Real fixture-backed HTTP checks returned 404 for all specified retired account/feedback routes; account GET/PATCH and collection create/list assertions passed. Edge H: unauthenticated and malformed-ID variants all returned `404 {"detail":"Not Found"}`, while retained `/api/v1/me` returned `401 {"detail":"missing bearer token"}`. |
| AC6 | UNVERIFIED | B/O passed `test_recommendation_personalization_removal.py`, but its two tests only inspect a signature/source string and an empty stub connection's SQL. They never seed the named pet/avoid/archetype/notes/flags/extreme-weights/quota/feedback/cross-deck state, execute Builder/free-form/mana/swap retrieval, or compare ordered card identities. Extra O run produced `12 passed, 111 deselected in 0.06s`, including structural/weak-card edges, but did not perform the required differential comparison. Empty Discover-exclusion input is exercised; extreme legacy-state and canonical/ordering comparisons remain unexercised even now that isolated PostgreSQL works. |
| AC7 | PASS | `docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py` → `1 passed in 2.20s`, `EXIT=0`. Captured real evaluator transport asserts no saved sentinels, unchanged new hashes, old advice invalidation, and historical-row retention. Actual database check `docker compose exec -T postgres psql -U mtg -d mtg_helper_test -c "SELECT count(*) AS current_assessments FROM new_card_assessments; SELECT input_hash, count(*) FROM new_card_assessment_history GROUP BY input_hash;"` → `current_assessments: 9`; history `personalized-old-context | 1`. Edge command: `docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py tests/test_new_cards_pilot.py -k 'legacy_rows_do_not_change_context_or_reuse_old_assessments or context_changes_hide_cache or legacy_personalization_rows_do_not_stale'` → `5 passed, 12 deselected in 5.14s`. Quantity, explicit goal, and rules changes still stale cached results, whereas legacy saved-state changes do not. |
| AC8 | UNVERIFIED | F passed the existing dismissal/undo, Discover report/planning, workspace and bounded-history checks, including network failure and obsolete-deck-response edges. But `components/personalization-removal.test.tsx` only renders a suggestion with no-op callbacks and tests absent API properties: no Builder Reject is clicked, no replacement/exclusion request is checked, and no fresh navigation session is tested. Two names asserted absent (`submitFeedback`, `getPreferences`) are not the removed methods (`addFeedback`, `listPreferences`). Browser edge: `playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/build` displayed `sign in required`; screenshot `artifacts/eval-2-builder.png` inspected, console `artifacts/eval-2-builder-console.txt` captured. No suggestions were available to reject. |
| AC9 | PASS | `. ./.agent/specs/remove-recommendation-personalization/artifacts/eval-2-retention-probe.ps1` ran the exact VERIFY container pytest command for `tests/test_personalization_data_retention.py` → `1 passed in 1.83s`, `PYTEST_EXIT=0`. The test snapshots seven tables, applies schema twice, compares every stored row, and checks repeated guarded New Cards reads. Independent actual `psql` snapshots after an additional schema application returned `PSQL_SCHEMA_EXIT=0` and `THIRD_APPLY_SNAPSHOTS_EQUAL=True`; each of the four legacy tables plus accounts/decks/collections still had one row. Exact SQL, commands and per-table hashes are retained in the script and `artifacts/eval-2-retention-probe.log`, with before/after files. Edge: a third schema reapplication, beyond the required two, preserved identical snapshots. |

## Scope

Read the fixed-base diff, including source/retrieval coefficients, schema/history
changes, routing, UI/client contracts, deleted implementations, and test removals.
The fixed coefficients match the former default model (semantic+synergy = 0.47,
popularity = 0.10, source inclusions = 0.20 each; trusted quota = 1.0); no retuning
finding. Legacy table definitions are retained.

| Finding | Type | Evidence |
|---|---|---|
| S1 | UNREQUESTED | `docker-compose.prod.yml:42,55-57,105-108` in the fixed-base diff removes managed PostgreSQL, adds required `MTG_DATABASE_URL` and external `shared_database`. No personalization criterion requires changing production database topology. `git log --format='%h %s' BASE...HEAD -- docker-compose.prod.yml` returned `02639497 added missing network` and `c1b7e272 migrated to shared db`: these are inherited branch commits, not newly attributed to the feature builder. Report for human scope selection; **do not undo this unrelated work** (Non-goal 20 / preservation constraint). |
| S2 | VIOLATES | `frontend/lib/types.ts:713-720` still includes `"memory"` in `CommanderCoachResolvedMode`, used by `CommanderCoachResponse.mode`. Constraint: delete retired client contracts/modes; backend `models/ai.py` has removed the same mode. The edited frontend contract remains wider than the retired public response contract. |
| S3 | VIOLATES | Fixed-base diff of `backend/tests/test_assistant_sessions.py` deletes `test_background_turn_completes_after_start_response` and `test_background_failure_records_failed_turn` outright, not just their old memory storage hooks. No replacement background/stream failure tests exist in the three named AC2 suites. Constraint: preserve or replace retained behavior coverage, not only delete obsolete feature-only tests. Supplemental evaluator artifacts establish some runtime behavior but do not repair the implementation's lost regression coverage. |

## Precise builder feedback

1. Fix `test_retired_personalization_api.py:32`: `AsyncClient.get` does not accept
   `json`. Use the generic `client.request` seam or omit a body for GET. Rerun the
   entire named backend acceptance suite: Docker is now available and it exposes
   this deterministic failure; do not report it as merely Docker-blocked.
2. Remove the remaining frontend resolved `memory` mode and add a regression check
   against the supported response modes.
3. Replace AC1's property-only test with a rendered Assistant load/answer test that
   checks outgoing requests and memory controls. Complete the authenticated manual
   flow on isolated storage with a deterministic provider, without bypassing OAuth.
4. Implement AC6's real seeded before/after result comparison. Signature/source
   inspection and empty SQL stubs cannot prove unchanged result order or eligibility.
   Cover all listed retrieval/workflow paths, extreme settings and retained explicit
   constraints/canonical identity/source ordering.
5. Implement AC8's actual Builder action/navigation checks. The current no-op
   callbacks never exercise Reject. Assert the real removed method names or,
   preferably, observed HTTP requests. Verify replacement, local exclusion, no
   legacy feedback POST, and a fresh rejection session after navigation.
6. Restore retained background/tracing/failure regression coverage at the model
   transport seam. The evaluator's supplemental probe shows a normal background
   turn and recoverable provider failure work today; retain that as product tests,
   rather than relying on an evaluation-only script.

## Cleanup and self-violation check

`playwright-cli -s=remove-recommendation-personalization close` returned
`Browser 'remove-recommendation-personalization' closed`. The host frontend process
tree was terminated. Final `docker compose down` returned `COMPOSE_DOWN_EXIT=0`;
only local containers/networks were removed, no volumes. Final listener query for
3000/8000/5432 returned no entries. No app/model process or browser session was left
running.

`git status --porcelain` before and after testing has the same preexisting changes
outside this spec directory (AGENTS/README, config/main/conftest, base Compose,
live-data-development artifacts, example env/VERIFY/check_database/safety-test/live
override files). New evaluator files are only in this spec directory. **No observed
self-violation; unrelated changes were not reverted.** Full final status is in
`artifacts/eval-2-status.txt`.

## Build-notes comparison

Read `build-notes.md` only after writing the verdicts above. Its original Docker
blocker was reproducible initially, but became stale during this evaluation: the
later isolated run completed and exposed the memory test's `TypeError`. Its claim
that the retired API test verifies real Assistant response fields is not presently
achieved by that test, because the invalid GET invocation stops it first. The
Builder test really does retain Reject rendering, as claimed, but does not prove
the required Reject behavior, and two absent-method assertions use the wrong names.
The New Cards historical-row and data-retention claims were independently exercised
successfully once PostgreSQL became available. The focused/frontend results do not
contradict its reported 108 frontend passes; the evaluator did not independently
rerun the claimed complete 522-test offline selection or all lint/build tools.

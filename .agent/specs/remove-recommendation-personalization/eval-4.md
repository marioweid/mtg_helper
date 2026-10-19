# Evaluation — round 4

**Overall: FAIL / manual portions deferred.** The two concrete eval-3 findings are
fixed and their corrected checks pass. The complete named backend selection passes
**42 tests**, and frontend passes **108 tests**. A new reproducible **test-collection
order defect** remains in the New Cards acceptance test (AC7), detailed below.
Authenticated browser portions of AC1/AC4/AC8 remain **UNVERIFIED**, explicitly
deferred by the user's "Skip manual checks" decision, not silently passed.

## Boundary and safety

Read the approved spec/verify methods and VERIFY.md again before testing; project
AGENTS and eval-3 remain applicable. Feature base is
`02639497394d0fe1d8e8baf25617fd8c2c0a1e8b`; HEAD is
`2fbd94e3054673fa94fcdaf07cfa70268b8d4fe8`, plus the working-tree continuation.
Preserved eval-3 as historical evidence. Scope diff saved as
`artifacts/eval-4-scope.diff`; correction diff as `eval-4-corrections.diff`.

Main explicitly granted exclusive disposable database access for this round. Used
only base Compose, fixed `mtg_helper_test`, and `OPENAI_API_KEY=test`. No live override,
environment-file edits, application-source edits, auth bypass, paid provider calls,
or browser/frontend startup. Existing ASGI test identity and provider adapters are
not claimed to exercise production OAuth. No app lifespan/startup maintenance ran.

## Exact commands and observed output

Compose commands ran at repo root; host Python commands from `backend/`; pnpm
commands from `frontend/`. Logs preserve raw output, including Docker progress on
stderr which PowerShell labels `NativeCommandError` despite Docker exit 0.

**Boot / target:**

```text
docker compose up -d --wait postgres
Container mtg_helper-postgres-1 Healthy
EXIT=0
docker compose exec -T postgres psql -U mtg -d postgres -Atc "SELECT datname FROM pg_database WHERE datname = 'mtg_helper_test'"
mtg_helper_test
EXIT=0
```

**B — named backend acceptance, independently executed:**

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_assistant_personalization_removal.py tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py tests/test_retired_personalization_api.py tests/test_recommendation_personalization_removal.py tests/test_new_cards_personalization_removal.py tests/test_personalization_data_retention.py
..........................................                               [100%]
42 passed in 12.66s
EXIT=0
```

Full raw log: `artifacts/eval-4-backend-acceptance.log`.

**F — named frontend checks (the script actually runs all 22 files):**

```text
corepack pnpm test -- app/decks/coach-personalization.test.tsx app/preferences/page.test.tsx components/personalization-removal.test.tsx components/card-workspace.test.tsx components/discover-state.test.ts components/new-cards-panel.test.tsx lib/coach-conversation.test.ts
Test Files 22 passed (22)
Tests 108 passed (108)
EXIT=0
corepack pnpm exec tsc --noEmit --incremental false
EXIT=0
```

Raw logs: `artifacts/eval-4-frontend.log`, `eval-4-types.log`. Final lint/build gates
are owned by main, not independently rerun here.

**S — focused sessions, including the two restored regression edges:**

```text
uv run --no-sync pytest -v -W error -m no_db tests/test_assistant_sessions.py tests/test_assistant_personalization_removal.py
tests/test_assistant_sessions.py::test_start_response_returns_while_background_turn_is_open PASSED
tests/test_assistant_sessions.py::test_uncaught_background_failure_streams_failed_event_and_failed_trace PASSED
12 passed in 0.29s
EXIT=0
```

Raw log: `artifacts/eval-4-sessions.log`. It also contains successful provider
recovery, unauthorized-deck, malformed-conversation, concurrent-session and
tracing-disabled tests.

**R — additional retrieval/structural edges:**

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_recommendation_personalization_removal.py tests/test_retrieval_service.py tests/test_deck_fit_service.py -k 'real_recommendation_outcomes or trusted_quota or empty_collection or underfilled_roles or known_combo'
15 passed, 109 deselected in 12.88s
EXIT=0
```

Raw log: `artifacts/eval-4-retrieval-edges.log`.

**H — additional real ASGI HTTP edges, no DB/auth override/lifespan:**

```text
uv run --no-sync python ../.agent/specs/remove-recommendation-personalization/artifacts/eval-3-http-probe.py
GET /openapi.json 200; retired_paths=[]; retired_models=[]
response_fields=['doctor', 'mode', 'recommendations', 'replacement', 'reply']
response_modes=['doctor', 'builder', 'mana', 'meta', 'chat', 'replacement']
unauthenticated GET /api/v1/decks/not-a-uuid/coach/memory 404 {"detail":"Not Found"}
unauthenticated PUT /api/v1/decks/not-a-uuid/coach/memory 404 {"detail":"Not Found"}
unauthenticated DELETE /api/v1/me/preferences/not-a-uuid 404 {"detail":"Not Found"}
unauthenticated DELETE /api/v1/decks/not-a-uuid/feedback/not-a-uuid 404 {"detail":"Not Found"}
unauthenticated GET /api/v1/me 401 {"detail":"missing bearer token"}
EXIT=0
```

Full log `artifacts/eval-4-http-edges.log` includes every retired verb for UUID and
malformed-ID variants; all retired responses are asserted 404.

**D — actual DB snapshots and a third schema application, after B's retention test:**

```text
. ./.agent/specs/remove-recommendation-personalization/artifacts/eval-4-retention-probe.ps1
mtg_helper_test|mtg|16.14 (Debian 16.14-1.pgdg13+1)
preferences|1|860b00e60b8f39ec0d6284379709d8d8
account_ranking_weights|1|6ef9b24779b430417925367a0c7e34f5
deck_feedback|1|de6ec9d83df0795857852b41362b4e3a
deck_coach_memory|1|dcf402da6c733b3cbee3ee0f10ac3cd3
accounts|1|cd559f3b288061a9bb7a351788d77883
decks|1|11648293c2314df8c46cca0c827af9b0
collections|1|24b68e312b106a4e35ee04b1d95c4180
PSQL_SCHEMA_EXIT=0
THIRD_APPLY_SNAPSHOTS_EQUAL=True
```

Script contains exact `psql` queries and asserts exit codes; full before/after rows
and schema output are saved in `artifacts/eval-4-retention-*` and
`eval-4-schema-third-apply.log`. All seven after hashes equal the displayed before
hashes, not just their row counts.

## Acceptance — automated versus deferred browser portions

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 automated | PASS at page/action HTTP module seam | F → `Tests 108 passed (108)`, including the 2 Assistant tests. Reviewed corrected `not.toContainEqual(expect.stringMatching(/memory/i))` guards at `coach-personalization.test.tsx:218-220,276-278`. Actual page/conversation functions load a deck, invoke Send and the real API client, accept a deterministic SSE result, and render `Add more early ramp.` with no memory controls. Edge: second turn sends the preceding user/assistant history. Main reports actual retired-fetch mutations made both workflow tests fail at their network guards, then were removed; this evaluator reviewed the corrected guards and independently reproduced the green suite, not main's mutations. |
| AC1 manual/framework | UNVERIFIED — user deferred | No browser command, screenshot or console captured this round. Node hook scheduling/static markup is not a React client mount or authenticated isolated-stack browser answer. The user explicitly selected "Skip manual checks"; do not retry sign-in or infer PASS from the module test. |
| AC2 automated | PASS | B → `42 passed in 12.66s`; S → `12 passed in 0.29s`. The new external `DelayedModel` holds provider work after `/coach/start` returns; root trace is unfinished until release, then ends successfully. Infrastructure `FailingProgressQueue/Registry` raises during real progress publication, producing `event: failed`, failed root span and no output. Existing deterministic history/doctor/grounding/progress/recovery checks also pass. Edges: malformed conversation, unauthorized deck, parallel sessions and disabled tracing all pass in S. Eval-3 S2 is resolved; business orchestration is not mocked in the restored cases. |
| AC3 automated | PASS | B executes authenticated owned-fixture GET/PUT `/coach/memory` → asserted 404, OpenAPI checks and a real deterministic Assistant response without retired fields. The previous `AsyncClient.get(json=...)` error does not recur. H independently reports no retired routes/models/fields/mode and malformed/unauthenticated GET/PUT → `404 {"detail":"Not Found"}`. |
| AC4 automated | PASS at static page/navigation seam | F → `Tests 108 passed (108)`. Expanded `app/preferences/page.test.tsx:11-25` renders actual Preferences and actual async Nav with external auth adapter, asserts `/preferences` anchor, heading/copy, no form/input/select/textarea/button on the page and zero fetch calls. Edge: Nav is rendered with `auth() → null`, retaining the link without assuming an authenticated session. This verifies the requested static module behavior, not middleware/OAuth or client-side effect scheduling. |
| AC4 manual/framework | UNVERIFIED — user deferred | No browser visit/screenshot/console this round. Prior normal-secret browser attempts reached sign-in; actual authenticated empty-state navigation remains unavailable by explicit user choice. |
| AC5 automated | PASS | B includes all retired preferences/weights/legacy-feedback verbs and retained account GET/PATCH plus collection create/list on real local DB fixtures. H's unauthorized/malformed-ID edge variants return `404 {"detail":"Not Found"}`; retained account endpoint without bearer token returns `401 {"detail":"missing bearer token"}`. |
| AC6 automated | PASS | B and R execute the real seeded differential (`test_recommendation_personalization_removal.py:175-269`), not signature/source/empty-storage stubs. Real Builder/free-form/mana/swap HTTP ordered identities, fit, New Cards candidates and Discover preview exclusions match before/after extreme legacy records. Nonempty-membership assertions prevent empty-result false positives. Edges: explicit exclusion, noncanonical reprint, source tags, unprotected pet fit; R additionally passes trusted ordering, zero-limit/missing-card/empty-collection cases, underfilled-role and combo protection (`15 passed, 109 deselected in 12.88s`). |
| AC7 automated | FAIL — test-collection order edge; named runtime behavior PASS | B → `42 passed`; standalone exact verify later → `1 passed in 2.00s`. Real cache/history behavior succeeds, including retained old row confirmed by `psql` below. But collecting `test_new_cards_pilot.py` before the new acceptance file deterministically produces `fixture 'pilot' not found`; minimal repro → `16 deselected, 1 error in 1.80s`, `EXIT=1`. Reversing only file order → `5 passed, 12 deselected in 4.67s`, `EXIT=0`. This is a real test-deliverable defect, not a reproduced cache-product malfunction. |
| AC8 automated | PASS at page/action HTTP module seam | F → `Tests 108 passed (108)`. Builder now executes queued mount effects, waits for actual card state, rejects/replaces locally, sends excluded name on Load More, checks no feedback/preferences/weights requests with corrected `toContainEqual`, and starts a manually fresh instance for deck-2. Stronger pet-heart markup pattern is checked. Named retained New Cards dismissal/undo, Discover incorrect-report/planning, workspace and bounded-history checks pass; their failed-read/stale-response/retry edges run too. Framework navigation/remount is explicitly outside this node harness, not claimed PASS. |
| AC8 manual/framework | UNVERIFIED — user deferred | No browser workflow/screenshot/console this round. Fake-hook reset before deck-2 is a simulated remount; it does not prove actual React/Next navigation. Full authorized deck/Builder actions remain deferred. |
| AC9 automated/DB | PASS | B executes real SQL seed/snapshots of all seven required tables, schema twice and repeated guarded New Cards reads. D directly `psql`s actual rows and applies schema a third time: `PSQL_SCHEMA_EXIT=0`, `THIRD_APPLY_SNAPSHOTS_EQUAL=True`; all four legacy and three unrelated tables retain identical hashes. No live database or inferred log-only DB evidence used. |

## New concrete issue: order-sensitive fixture registration

Minimal reproducible command (repo root):

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_pilot.py tests/test_new_cards_personalization_removal.py -k legacy_rows_do_not_change_context_or_reuse_old_assessments
E       fixture 'pilot' not found
ERROR tests/test_new_cards_personalization_removal.py::test_legacy_rows_do_not_change_context_or_reuse_old_assessments
16 deselected, 1 error in 1.80s
EXIT=1
```

Logs: `eval-4-newcards-order-repro.log`; original broader failure is in
`eval-4-newcards-edges.log` (`4 passed, 12 deselected, 1 error in 5.72s`).

Order-only control:

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py tests/test_new_cards_pilot.py -k 'context_changes_hide_cache or legacy_personalization_rows_do_not_stale or legacy_rows_do_not_change_context_or_reuse_old_assessments'
5 passed, 12 deselected in 4.67s
EXIT=0
```

Root cause: new `test_new_cards_personalization_removal.py:5` registers the **test
module** `tests.test_new_cards_pilot` as a plugin to borrow `pilot`/`model`. When
that module has already been collected, pytest has registered its fixtures with
module-local visibility. Installed pytest's `FixtureManager.parsefactories`
(`backend/.venv/Lib/site-packages/_pytest/fixtures.py:1708-1726`) returns immediately
for a previously seen holder object instead of registering it globally on later
plugin registration. Consequently the sibling acceptance module cannot see its
fixtures. Register shared fixtures before test collection (a proper shared fixture
module/conftest), rather than depending on which test file is listed first. No
fix or test loosening was performed by this evaluator.

Standalone runtime verification and DB evidence after reproduction:

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py
1 passed in 2.00s
EXIT=0
docker compose exec -T postgres psql -U mtg -d mtg_helper_test -c "SELECT count(*) AS current_assessments FROM new_card_assessments; SELECT input_hash, count(*) FROM new_card_assessment_history GROUP BY input_hash;"
 current_assessments
---------------------
                   9
(1 row)

        input_hash        | count
--------------------------+-------
 personalized-old-context |     1
(1 row)
EXIT=0
```

Logs: `eval-4-newcards-standalone.log`, `eval-4-history-final-db.log`. The initial
failed setup reset the disposable fixture database and yielded zero assessments;
that first empty query is retained in `eval-4-history-db.log` and is **not** used
as evidence of preservation. The successful standalone run is the final DB result.

## Framework limitations (not hidden failures or browser approval)

Frontend tests execute real pages, handlers, request clients and child static
rendering, with external HTTP/SSE/auth adapters. Their business action coverage is
now accepted at the approved module seam. They still replace React hooks and invoke
functions manually, so do not verify the client scheduler, hydration, effect
dependency/cleanup semantics, DOM event dispatch, routing keys or OAuth. The
Builder effects omission and broken negative request guards from eval-3 are fixed;
simulated remount remains accurately labeled. No screenshot/console requirement is
waived by a node test. Manual portions stay UNVERIFIED without further sign-in attempts.

## Scope

none

Rechecked the supplied feature-base diff and working-tree continuation against
Constraints/Non-goals. No new endpoint, flag, dependency, recommendation retuning,
compatibility shim or forbidden deletion found. The two eval-3 scope violations
(ineffective guards and missing retained background regression) are corrected.
The new AC7 test-order defect above is a verification defect, not an unrequested
product feature. Preexisting live-development edits remain untouched; inherited
production topology is outside this feature-base diff, not a new scope finding.

## Cleanup / self-violation / build-notes

```text
docker compose down
Container mtg_helper-postgres-1 Removed
Network mtg_helper_default Removed
EXIT=0
git status --porcelain
[full output saved to artifacts/eval-4-status-after.txt]
Compare-Object $before $after
[no output; both lists exclude only this spec directory]
STATUS_COMPARE_COMPLETED=True
Get-NetTCPConnection -State Listen -LocalPort 3000,3001,8000,5432 -ErrorAction SilentlyContinue
[no output]
LISTENER_CHECK_COMPLETED=True
```

Raw shutdown log: `artifacts/eval-4-stop.log`; initial/final status lists are in
`eval-4-status-before.txt`/`eval-4-status-after.txt`. No volumes were deleted. No
browser/frontend was started; no browser session was opened or left behind. All
evaluator writes are `eval-4.md` and artifacts under this spec directory. Outside
that directory status is unchanged: **no observed self-violation**, no unrelated
edits reverted. Main updated build-notes concurrently within the spec directory;
this evaluator did not edit it.

Read current `build-notes.md` only after writing verdicts. Its corrected network
guards, expanded module checks and restored background checks match inspection and
the passing runs here. Its pending final backend count is now independently **42**.
Its browser limitations are accurately qualified. The historical Docker-blocked
notes are not the current result. Whole offline suite, 226-test broader regression
and final production build/static gates are main-reported and were not independently
rerun here. The notes do not mention the new order-sensitive fixture defect, which
this evaluation reproduces and reports above.

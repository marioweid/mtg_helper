# Evaluation — round 3 continuation

**Overall: not approved.** Authenticated manual portions of AC1/AC4/AC8 are
**UNVERIFIED, explicitly deferred by the user ("Skip manual checks")**. Do not
interpret that choice as a browser PASS. Two concrete automated-coverage findings
remain below; no new application malfunction was reproduced in the permitted runs.

## Boundary and execution

- Read AGENTS.md, VERIFY.md, approved spec.md (including every verify method), and
  eval-2.md before testing. No build-notes read before recording these verdicts.
- Feature base: `02639497394d0fe1d8e8baf25617fd8c2c0a1e8b`; HEAD:
  `2fbd94e3054673fa94fcdaf07cfa70268b8d4fe8`, **plus the working-tree continuation**.
  Inspected both `git diff BASE...HEAD` and `git diff BASE`/`git diff HEAD`.
  The old eval's production-topology finding used the wrong feature boundary:
  `git diff BASE...HEAD -- docker-compose.prod.yml` now returns **no output**.
- Per coordination instructions, **did not boot frontend/backend/browser, start or
  stop containers, or run any DB-resetting pytest session**. Main may be using the
  disposable `_test` DB. No auth bypass or paid model request was introduced.
  Existing deterministic test fixtures substitute the identity/storage/provider
  seams; they do not establish production OAuth behavior.
- Main supplied the result **"named backend acceptance 40 passed"** on VERIFY's
  isolated Docker `_test` target. That is useful external evidence, not a command
  independently executed by this evaluator. No current raw 40-pass log was available
  in artifacts during inspection. DB-only portions below are therefore explicitly
  distinguished from independently observed results, not reported as fresh PASSes.

## Commands and exact observed output

Commands F/T/L ran from `frontend/`; O/E/H from `backend/`; M from the repo root.
The named frontend command actually selects **all 22 files**, as in round 2.

**F — named frontend checks:**

```text
corepack pnpm test -- app/decks/coach-personalization.test.tsx app/preferences/page.test.tsx components/personalization-removal.test.tsx components/card-workspace.test.tsx components/discover-state.test.ts components/new-cards-panel.test.tsx lib/coach-conversation.test.ts
app/decks/coach-personalization.test.tsx (2 tests)
components/personalization-removal.test.tsx (1 test)
app/preferences/page.test.tsx (1 test)
Test Files 22 passed (22)
Tests 108 passed (108)
EXIT=0
```

Full output: `artifacts/eval-3-frontend-tests.log`.

**O — focused offline backend:**

```text
uv run --no-sync pytest -q -W error -m no_db tests/test_assistant_personalization_removal.py tests/test_assistant_sessions.py tests/test_commander_coach_pipeline.py tests/test_retrieval_service.py tests/test_deck_fit_service.py
46 passed, 111 deselected in 0.37s
EXIT=0
```

**E — explicit session/edge rerun:**

```text
uv run --no-sync pytest -v -W error -m no_db tests/test_assistant_sessions.py tests/test_assistant_personalization_removal.py
tests/test_assistant_sessions.py::test_background_turn_streams_progress_and_preserves_tracing PASSED
tests/test_assistant_sessions.py::test_background_provider_failure_streams_recoverable_answer PASSED
tests/test_assistant_sessions.py::test_unauthorized_deck_and_invalid_conversation_never_create_turn PASSED
tests/test_assistant_sessions.py::test_sessions_isolate_accounts_decks_and_parallel_chats PASSED
10 passed in 0.22s
EXIT=0
```

Full outputs: `artifacts/eval-3-offline.log`, `eval-3-session-edges.log`.

**H — real in-process FastAPI HTTP edge probe, no lifespan/DB/auth override:**

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

The probe also asserts and prints all retired verbs with UUID and malformed-ID
variants. Full exact script/output: `artifacts/eval-3-http-probe.py`/`.log`.
Its UUID is **not** claimed to be an owned fixture deck.

**M — reproduce the ineffective frontend network assertion with installed matcher:**

```text
node .agent/specs/remove-recommendation-personalization/artifacts/eval-3-matcher-probe.mjs
BROKEN_GUARD_PASSED_WITH_RETIRED_REQUEST=/api/v1/decks/deck-1/coach/memory
TO_CONTAIN_EQUAL_REJECTS_SAME_REQUEST=true
BROKEN_GUARD_PASSED_WITH_RETIRED_REQUEST=/api/v1/decks/deck-1/feedback
TO_CONTAIN_EQUAL_REJECTS_SAME_REQUEST=true
EXIT=0
```

This loads the installed Vitest 3.1.2 Chai plugin and `StringMatching`, not a mocked
matcher. `.not.toContain(asymmetricMatcher)` does an identity containment check;
`.not.toContainEqual(asymmetricMatcher)` detects the same retired URL correctly.

**T/L — ancillary static gates:**

```text
corepack pnpm exec tsc --noEmit --incremental false
EXIT=0
corepack pnpm lint
Found 0 warnings and 0 errors.
LINT_EXIT=0
corepack pnpm format:check
All matched files use the correct format.
Finished in 12ms on 139 files using 16 threads.
FORMAT_EXIT=0
```

No production build rerun: main reports builder's successful build; starting one
was unnecessary for this evaluation and could conflict with concurrent work.

## Acceptance — automated versus manual

UNVERIFIED counts as failure for independent sign-off. "Main reports PASS" is
provenance, not a substitute for this evaluator exercising the DB verify method.

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 automated | UNVERIFIED (partial behavior passes) | F → `Tests 108 passed (108)`. The actual Assistant page/conversation function, request client, Send handlers and streamed-result handling now execute; static markup contains `Test Deck` and `Add more early ramp.` and the second HTTP body contains both prior turns (`coach-personalization.test.tsx:208-274`). This repairs the property-only test. However M → `BROKEN_GUARD_PASSED_WITH_RETIRED_REQUEST=/api/v1/decks/deck-1/coach/memory`; its no-memory network guard is ineffective. Hooks/effects are simulated, not a React client mount. Edge: follow-up history is exercised, but no empty-input/load-failure browser edge was run. |
| AC1 manual | UNVERIFIED — user deferred | No browser command run this round. Existing `browser-3.md` records `goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/coach` → `Page URL: http://localhost:3000/signin?callbackUrl=%2Fdecks%2F00000000-0000-4000-8000-000000000001%2Fcoach`. That is an auth gate, not a deck answer. No fresh screenshot/console or authenticated deterministic-provider page check; no retries authorized. |
| AC2 automated | PASS for exercised behavior; regression constraint finding S2 remains | O → `46 passed, 111 deselected in 0.37s`; E → `10 passed in 0.22s`. Real ASGI sync/start/SSE plus deterministic model transport verify normal progress, tracing, history, ordinary remember/forget and separate doctor context. Edge outputs in E include unauthorized/malformed conversation, parallel isolated chats, tracing-disabled mode, and provider-failure recovery, all `PASSED`. S2 explains what the restored tests still do not cover. |
| AC3 automated | UNVERIFIED independently for owned-deck portion; main reports PASS | H → `retired_paths=[]; retired_models=[]`, no memory response fields/mode, malformed and unauthenticated GET/PUT → `404 {"detail":"Not Found"}`. Reviewed fix at `test_retired_personalization_api.py:32`: `client.request(method, ..., json={})` replaces invalid `client.get(..., json={})`; the actual deterministic answer assertion at lines 35-42 is now reachable. Main's supplied acceptance result is `40 passed`; this evaluator intentionally did not run the reset-DB verify command. The eval-2 TypeError has been corrected, not reproduced. |
| AC4 automated | UNVERIFIED for full requested checks; static copy PASS | F → `app/preferences/page.test.tsx (1 test)` passed: both exact paragraphs and heading are rendered. The 15-line test does not import/render Nav, capture HTTP requests, or assert absence of all forms/toggles. It only excludes three text strings (`page.test.tsx:9-14`); no new edge probe exercises the complete criterion. |
| AC4 manual | UNVERIFIED — user deferred | No browser command run. `browser-3.md`: `open http://localhost:3000/preferences` → `Page URL: http://localhost:3000/signin?callbackUrl=%2Fpreferences`. Prior screenshots/console show sign-in and retained nav, not authenticated empty state. Do not carry eval-2's MissingSecret-era exposed-page PASS forward as authenticated validation. |
| AC5 automated | UNVERIFIED independently for authenticated retained operations; main reports PASS | H prints/asserts every retired verb as `404 {"detail":"Not Found"}`, including malformed IDs; retained unauthenticated `/api/v1/me` → `401 {"detail":"missing bearer token"}`. The fixture-backed account GET/PATCH and collection check is unchanged from eval-2 and included in main's reported `40 passed`, but not rerun here. No DB operations were authorized concurrently. |
| AC6 automated | UNVERIFIED independently at real DB seam; main reports PASS; test design materially repaired | Reviewed `test_recommendation_personalization_removal.py:175-269`: real SQL now seeds all named tastes, flags, extreme weights/quota, up/down/reject, and cross-deck state, then compares `_outcomes` before/after. `_outcomes` issues real build/suggest/mana-fix/swap/deck HTTP calls, loads real New Cards candidates and calls real Discover preview; it does **not** mock retrieval logic. Nonempty-membership assertions prevent an all-empty false pass. Edge assertions cover explicit exclusion, noncanonical reprint omission and unprotected pet fit. Main reports the complete named suite `40 passed`; this evaluator did not independently execute this destructive DB verify. This is no longer the old signature/empty-SQL stub. |
| AC7 automated | UNVERIFIED independently this round; main reports PASS | Real DB/provider test is unchanged: compares context hashes after legacy seeds, forces `personalized-old-context`, verifies stale advice, reruns deterministic evaluator and checks retained history/prompt sentinels. Previously executed eval-2 command `docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py` → `1 passed in 2.20s`; main now reports named acceptance `40 passed`. No fresh DB/cache-context edge executed here. |
| AC8 automated | UNVERIFIED (partial actions pass) | F → `Tests 108 passed (108)`. New test executes real Builder reducer, Reject callback, local buffered replacement, and Load More request body containing `Rejected Card` in `exclude`; retained New Cards dismissal/undo and stale-read/network-failure tests, Discover Report incorrect/planning controller tests, and bounded history run too. But M → `BROKEN_GUARD_PASSED_WITH_RETIRED_REQUEST=/api/v1/decks/deck-1/feedback`. Builder test never runs its queued mount effects; no deck-detail page load or actual filter interaction is exercised. Fresh navigation is simulated by `hooks.reset()` before changing IDs, not performed through React/Next. |
| AC8 manual | UNVERIFIED — user deferred | No browser command run. `browser-3.md`: `goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/build` → sign-in URL. No authorized Reject/navigation/filter/New Cards/Discover browser workflow or screenshot/console was captured by this evaluator. |
| AC9 automated/DB | UNVERIFIED independently this round; main reports PASS | Unchanged real retention test snapshots seven tables and applies schema twice, then checks repeated guarded New Cards reads. Prior exact evidence in eval-2 retention probe: `1 passed in 1.83s`, `THIRD_APPLY_SNAPSHOTS_EQUAL=True`. Main reports named acceptance `40 passed`. No fresh `psql`, extra schema reapply, or broader legacy-read/write edge executed here; main owns the shared local test session. |

## Concrete findings and limitations

1. **Fix network assertions (AC1/AC8).** Use `not.toContainEqual(expect.stringMatching(...))`
   or `expect(urls.some(url => pattern.test(url))).toBe(false)`, then prove the check
   fails when a retired URL is present. Current negative assertions are vacuous:
   `coach-personalization.test.tsx:218,274` and
   `personalization-removal.test.tsx:260-262`. Do not claim these guards verified
   retired-request absence merely because all 108 tests pass.
2. **Restore retained background failure/timing regression.** The new success and
   recoverable-provider tests pass, but a provider exception is caught by the Assistant
   and becomes `event: done` with fallback text (`test_assistant_sessions.py:239-259`).
   It does not replace the deleted test for `event: failed`, failed span status and no
   output, nor the delayed-work assertion that the start response arrives while the
   turn is still open. Add those at an external adapter seam, without restoring memory.
3. **Framework coverage is not browser coverage.** AC1 and Builder tests import real
   page/handler/business functions and traverse the real API client to a fetch adapter:
   useful **page/action HTTP module-seam tests**, not display-only mocks anymore.
   They replace `useState/useReducer/useEffect/useCallback/useMemo` and manually rerun
   functions. They do **not** exercise React's client scheduler, effects/dependency
   semantics, hydration, event dispatch, Next routing/remount keys, OAuth or deployment
   networking. Builder's `mountBuilder` clears the whole fake hook store itself
   (`:199-211`), so the navigation assertion proves a manually fresh instance only.
   Its queued mount effects are never executed. Report these limitations even after
   correcting the request matchers; user-deferred manual portions remain UNVERIFIED.
4. AC3's deterministic GET TypeError and the frontend `"memory"` resolved mode from
   eval-2 are corrected. AC6 now has a substantive real seeded differential check.
   There is no observed new endpoint, dependency, ranking retuning or compatibility shim.

## Scope

Inspected fixed-base source/contract/UI/schema/test diff and continuation. Legacy
tables remain; superseded-assessment history supports the explicit retention criterion.
Fixed coefficients retain the old effective defaults (semantic+synergy 0.47,
popularity 0.10, source inclusion 0.20 each, trusted-first quota 1.0).
Unrelated preexisting live-development edits (AGENTS/README/config/main/conftest/
Compose and associated untracked files) are preserved and excluded from feature blame.
Production topology is inherited at the supplied base and is **not a finding**.

| Finding | Type | Evidence |
|---|---|---|
| S1 | VIOLATES | `frontend/app/decks/coach-personalization.test.tsx:218,274`, `frontend/components/personalization-removal.test.tsx:260-262`: ineffective asymmetric `toContain` guards, reproduced by M. Spec constraint: add behavioral checks and prove a relevant check fails under a plausible mutation. These guards pass with exactly the prohibited request present. |
| S2 | VIOLATES | `backend/tests/test_assistant_sessions.py:212-259` replaces deleted delayed-work/failed-background tests with immediate success and recoverable-provider tests. `git show BASE:backend/tests/test_assistant_sessions.py` shows former assertions for an open delayed turn, `event: failed`, `turns[0].status.is_ok is False`, and absent `gen_ai.output.messages`; none is covered by the new tests. Spec constraint: preserve or replace retained behavior coverage; AC2 explicitly retains failure handling/tracing. |

## Cleanup and self-violation check

No frontend, backend, browser or container was started by this evaluator. The HTTP
probe is in-process without lifespan and exits normally. Did not stop main's DB or
Rancher Desktop, nor retry the explicitly deferred OAuth/browser checks.

Initial status: `artifacts/eval-3-status-before.txt`. Final status check and
build-notes comparison are recorded below after verdicts.

```text
git status --porcelain
[full output saved in artifacts/eval-3-status-after.txt]
Compare-Object $before $after
[no output; both lists exclude only .agent/specs/remove-recommendation-personalization/]
STATUS_COMPARE_COMPLETED=True
Get-NetTCPConnection -State Listen -LocalPort 3000,3001,8000 -ErrorAction SilentlyContinue
[no output]
LISTENER_CHECK_COMPLETED=True
```

The status comparison script is the exact PowerShell pipeline executed in the
evaluation transcript; initial/final lists outside this spec directory are identical.
All evaluator-created files are `eval-3.md` or under this spec's `artifacts/`.
**No observed self-violation; no unrelated path was edited or reverted.** The
`--incremental false` typecheck avoids writing the tracked incremental build state.

## Build-notes comparison (read after testing/verdicts)

Read the existing round-2 `build-notes.md` only after writing the acceptance/scope
tables. Its Docker-blocked claim is stale: eval-2 already recorded working isolated
Docker later, and main now reports 40 backend acceptance passes. This evaluator's
DB omission is a deliberate coordination restriction, not a Docker failure.
Its old frontend description (absent API properties/Reject rendering) is superseded
by actual handler/request workflows in the continuation, with the matcher/framework
limitations documented above. Its 108 frontend passes are independently reproduced;
the old whole-backend count and production build were not independently rerun here.
No build-notes or report.md changes were made.

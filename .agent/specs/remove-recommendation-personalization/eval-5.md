# Evaluation — round 5 narrow follow-up

**Final automated verdict: PASS. No unresolved automated findings from this
evaluation.** Eval-4's collection-order failure is independently fixed in both
orders. Other automated verdicts carry forward the independently executed eval-4
checks, not an inference from main's new gate counts. Manual/framework portions of
AC1/AC4/AC8 remain **UNVERIFIED — explicitly user-deferred**. This is not full browser
acceptance, nor a request to resume the manual checks the user chose to skip.

## Scope and safety

Narrow follow-up to eval-4 only: inspect shared fixture extraction/callers and rerun
the two minimal collection-order reproductions. Read current VERIFY's isolated DB
and cleanup instructions before testing. Approved spec/acceptance methods, project
AGENTS and previous evals remain applicable. Feature boundary stays
`02639497394d0fe1d8e8baf25617fd8c2c0a1e8b` to HEAD `2fbd94e3` plus continuation.

Main granted exclusive use of the already-running disposable PostgreSQL. All tests
used VERIFY's base Compose/fixed `mtg_helper_test` and `OPENAI_API_KEY=test`. No
shared/live access, DSN/env/application-source changes, paid model calls, auth
bypass, commits or browser startup. Eval-3/eval-4 were preserved.

## Independently executed commands

Commands below ran from the repository root. Full raw output is under this spec's
`artifacts/`. Docker progress on stderr is displayed by PowerShell as
`NativeCommandError`, but actual Docker/test exit codes below are zero.

```text
docker compose exec -T postgres psql -U mtg -d postgres -Atc "SELECT datname FROM pg_database WHERE datname = 'mtg_helper_test'"
mtg_helper_test
TARGET_EXIT=0
```

**Formerly failing order:**

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_pilot.py tests/test_new_cards_personalization_removal.py -k legacy_rows_do_not_change_context_or_reuse_old_assessments
.                                                                        [100%]
1 passed, 16 deselected in 2.65s
PILOT_FIRST_EXIT=0
```

Raw log: `artifacts/eval-5-pilot-first.log`.

**Reversed order / control:**

```text
docker compose run --rm --no-deps -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error tests/test_new_cards_personalization_removal.py tests/test_new_cards_pilot.py -k legacy_rows_do_not_change_context_or_reuse_old_assessments
.                                                                        [100%]
1 passed, 16 deselected in 2.63s
ACCEPTANCE_FIRST_EXIT=0
```

Raw log: `artifacts/eval-5-acceptance-first.log`. The first ordering is the exact
eval-4 edge that returned `fixture 'pilot' not found`; it now reaches and passes
the actual cache/prompt/history assertions. No test skips or softened assertions.

**Actual database confirmation after the second run:**

```text
docker compose exec -T postgres psql -U mtg -d mtg_helper_test -c "SELECT count(*) AS current_assessments FROM new_card_assessments; SELECT input_hash, count(*) FROM new_card_assessment_history GROUP BY input_hash;"
 current_assessments
---------------------
                   9
(1 row)

        input_hash        | count
--------------------------+-------
 personalized-old-context |     1
(1 row)
PSQL_EXIT=0
```

Raw log: `artifacts/eval-5-history-db.log`. Old personalized advice remains an
actual historical row alongside nine current assessments, not only a log claim.

## Inspection of the correction

- `backend/tests/new_cards_fixtures.py:22-152` contains the extracted deterministic
  `ModelTransport`, external-provider `model` fixture and real SQL/catalog `pilot`
  fixture. Comparing with the former definitions shows retained behavior, with type
  annotations/docstrings and an explicit non-null account assertion added. Only the
  external OpenAI HTTP transport is substituted; New Cards evaluation, publication,
  cache identity and historical-row logic remain real.
- `backend/tests/conftest.py:24` registers
  `pytest_plugins = ("tests.new_cards_fixtures",)` at collection startup. The
  surrounding preexisting local/live safety validation remains present; this fix
  does not replace/reset conftest or its safety rules.
- `test_new_cards_pilot.py` no longer defines those fixtures;
  `test_new_cards_personalization_removal.py` no longer registers a test module as a
  plugin; `test_new_cards_completion.py` no longer aliases fixtures borrowed from
  that test module. All request fixtures by name through the shared registration.
- Search `pytest_plugins|test_new_cards_pilot as|fixtures\.(model|pilot)|new_cards_fixtures|ModelTransport`
  across `backend/tests/*.py` returned only the shared registration and definitions
  in `new_cards_fixtures.py`; no old test-module-as-plugin/borrowed aliases remain.

## Acceptance status

This is a narrow follow-up, not a claim that all suites were rerun again. B/F/S/R/D
below are the exact independently executed commands/outputs recorded in eval-4.

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 automated | PASS, carried forward | Eval-4 F named frontend command → `Test Files 22 passed (22)`, `Tests 108 passed (108)`; actual Assistant page/action HTTP adapter and corrected no-memory guards. No page/action source changed for this fixture correction. |
| AC1 manual/framework | UNVERIFIED — user-deferred | No browser command, screenshot/console or authenticated UI flow this round; no further manual evidence requested. |
| AC2 automated | PASS, carried forward | Eval-4 B named backend command → `42 passed in 12.66s`; S focused sessions → `12 passed in 0.29s`, including delayed-start and uncaught-failure/tracing edges. |
| AC3 automated | PASS, carried forward | Eval-4 B → `42 passed in 12.66s`; H HTTP probe → `retired_paths=[]; retired_models=[]` and malformed/unauthenticated memory GET/PUT → `404 {"detail":"Not Found"}`. |
| AC4 automated | PASS, carried forward | Eval-4 F → `Tests 108 passed (108)`; expanded real Nav/static Preferences checks assert retained link, exact empty state, absent controls and no fetch. |
| AC4 manual/framework | UNVERIFIED — user-deferred | No browser attempt or manual evidence requested. Static module rendering is not authenticated navigation. |
| AC5 automated | PASS, carried forward | Eval-4 B fixture-backed retired verbs/account/collection tests pass; H malformed/unauthenticated variants → 404 and retained unauthenticated `/me` → 401. |
| AC6 automated | PASS, carried forward | Eval-4 B real seeded ordered-results differential passes; R retrieval/structural edges → `15 passed, 109 deselected in 12.88s`. |
| AC7 automated | PASS — prior edge failure resolved | Both exact Docker commands above now produce `1 passed, 16 deselected`, exit 0. Same test exercises retained prompt/hash/cache/history logic. Actual `psql` yields nine current assessments and one `personalized-old-context` history row. File-order inversion supplies the previously failing edge, not only the original happy path. |
| AC8 automated | PASS, carried forward at module seam | Eval-4 F → `Tests 108 passed (108)` for real Builder effects/Reject/request actions and retained New Cards/Discover/history modules. Shared backend fixture extraction does not turn simulated React remounts into real routing evidence. |
| AC8 manual/framework | UNVERIFIED — user-deferred | No browser attempt/evidence requested; actual authenticated navigation/remount/workflows remain deferred by user choice. |
| AC9 automated/DB | PASS, carried forward | Eval-4 B retention check passes; direct D `psql` third schema apply → `PSQL_SCHEMA_EXIT=0`, `THIRD_APPLY_SNAPSHOTS_EQUAL=True` across all seven table snapshots. |

Main additionally reports combined shared-fixture/named suites **74 passed**, full
offline **527 passed**, and clean Ruff/format (240 files)/ty. Those additional gates
were not rerun in this narrow evaluation and are not substituted for the independent
commands above.

## Scope

none

The shared fixture module/early registration directly fixes the observed acceptance
test defect. No new product behavior, endpoint, dependency, flag or business-logic
mock was introduced. Preexisting live-development work is untouched. The inherited
production topology remains outside the supplied feature boundary.

## Cleanup and self-violation check

```text
docker compose stop postgres
Container mtg_helper-postgres-1 Stopped
STOP_EXIT=0
git status --porcelain
[full output saved to artifacts/eval-5-status-after.txt]
Compare-Object $before $after
[no output; both lists exclude only this spec directory]
STATUS_COMPARE_COMPLETED=True
```

Only the PostgreSQL service used for verification was stopped; no volumes, Compose
network, other services or container engine were removed/stopped. The one-off test
containers used `--rm`. No browser/frontend was started.

Initial/final status snapshots: `artifacts/eval-5-status-before.txt` and
`eval-5-status-after.txt`; raw service-stop log: `eval-5-stop-postgres.log`. All
evaluator-created files are inside this spec directory; outside it status is
unchanged. **No observed self-violation.**

## Build-notes comparison

Read current build-notes only after recording verdicts. Its manual-defer/framework
qualifications match this evaluation. It predates the shared-fixture correction and
still points to eval-4/pending backend recheck rather than this follow-up; this file
records the now-passing order reproductions without changing historical notes.
No contradiction with the independently observed test results; additional main-run
gate counts remain explicitly attributed above. No build-notes/report edits made.

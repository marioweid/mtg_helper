# Review — continuation round 3

## Scope selection

Review feature commits `234d0696` and `2fbd94e3` relative to
`02639497394d0fe1d8e8baf25617fd8c2c0a1e8b`, plus this continuation's relevant changes.
Inherited production-database topology and unrelated dirty live-development files are
not feature changes. Preserve them; do not revert them to satisfy a broader merge-base diff.

## Standards / maintainability

Independent reviewer inspected stable backend production changes and the current evaluation
corpus/scripts/operational docs. Found two low-severity stale parameters after removal:

1. `_stage_excluded_ids` still accepted an unused account ID.
2. Discover `exclusions` still accepted an unused owner.

Both parameters and all production call arguments were removed. A follow-up review confirmed
the reduced signatures match their callers, ownership checks remain, and there are no remaining
findings in those source diffs. Source lint/format/type checks passed afterward.

## Spec / behavior

`eval-4.md` independently exercised the corrected workflow module checks, real seeded database
comparisons, all named backend acceptance tests (**42 passed**), and the frontend suite
(**108 passed**). It confirmed the request-matcher and retained background-coverage findings
were fixed, then exposed a shared-fixture collection-order defect.

That defect was reproduced and fixed by moving New Cards fixtures into a dedicated module
registered before collection, removing test-module plugin/fixture borrowing. `eval-5.md`
independently ran both collection orders and confirmed real assessment/history behavior.
Its final automated verdict is **PASS**, with no unresolved automated findings.

Authenticated manual/framework portions of AC1/AC4/AC8 remain **UNVERIFIED**, explicitly
deferred by the user. Module/HTTP/static-markup checks do not prove real React scheduling,
Next navigation, OAuth, or authenticated browser workflows. Full ship acceptance is therefore
still blocked on deferred manual evidence; no further sign-in attempt is requested.

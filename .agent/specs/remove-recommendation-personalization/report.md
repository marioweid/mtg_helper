# Ship report: remove-recommendation-personalization

- Status: implementation complete; automated gates and independent automated evaluation PASS.
- Authenticated manual browser acceptance: deferred by the user (2026-10-18).
- Spec status: `blocked` for deferred manual acceptance only; no unresolved automated findings.
- Repository: `C:/Users/mario/sources/mtg_helper`.
- Branch: `mw/db_migration`.
- Feature baseline: `02639497394d0fe1d8e8baf25617fd8c2c0a1e8b`.
- Existing implementation commits: `234d0696` (round 1), `2fbd94e3` (round 2).
- Publication: user requested a feature-only commit and branch push on 2026-10-19.

## Resume point

The original missing-spec preflight blocker was resolved by restoring the approved spec.
An interrupted later run completed two implementation rounds and evaluations. `eval-2.md`
found a failing memory-route test, insufficient Assistant/Builder UI and recommendation
independence checks, a leftover frontend memory mode, and removed background-task coverage.
Round 3 addresses those findings rather than restarting the removal.

Use the feature baseline above for scope review: inherited production database-topology
commits and unrelated live-development working-tree changes must not be reverted or
attributed to this feature. Their preservation remains a requirement.

## Implemented

- Removed cross-chat Assistant memory, remember/forget routing, its editor/endpoints/models,
  and saved-memory prompt inputs, while retaining current-chat follow-ups and sessions.
- Removed account weights/mix, inferred taste profiles, pet/avoid preferences, legacy feedback
  collection and boosting throughout retrieval, deck-fit, New Cards and Discover exclusions.
- Kept account identity, ownership, explicit deck goals/filters, fixed source ordering,
  local Builder rejection, New Cards dismissal/undo and Discover quality reporting.
- Preferences remains in navigation with the approved empty-state copy.
- Retained legacy stored data; superseded personalized assessments are historical, not current.
- Updated the active evaluation corpus and operational documentation to match the removal.

## Verification

Actual commands and detailed results are in `gate-3.md`.

| Check | Observed result |
|---|---|
| Independent final named backend acceptance selection | 42 passed |
| Main expanded acceptance and New Cards shared-fixture selection | 74 passed |
| Main related isolated backend regression selection | 226 passed |
| Main final full offline backend selection | 527 passed, 793 deselected |
| Main final focused session selection | 10 passed |
| Main frontend suite | 108 passed across 22 files |
| Backend Ruff lint/format and source type check | Passed; 240 files formatted |
| Frontend lint/format/types/production build | Passed; zero lint warnings/errors |
| Source reviewer findings | Both unused personalization parameters fixed and rechecked |
| Authenticated full-browser workflows | Not verified; user explicitly deferred |

Selections overlap and are not a unique-test total. `eval-4.md` records independent backend,
frontend, session, retrieval, HTTP and real data-retention checks. Its fixture-order issue
was reproduced and fixed with a proper shared fixture module/early registration; `eval-5.md`
independently confirms both orderings and records the final automated PASS.

The evaluator's concrete round-3 test findings were addressed: negative URL assertions now
use asymmetric-aware matching; injecting real retired HTTP calls made the guards fail.
Delayed-turn and uncaught progress-publisher failure checks restore the removed regression
coverage without restoring saved memory. The current Preferences check also exercises the
navigation link, exact text, no settings controls and no requests at the module seam.

Frontend checks execute real page/action/client logic with framework and HTTP adapters and
static markup; they do not establish real React hydration, Next routing, OAuth, or browser
event/lifecycle correctness. Do not equate them with the deferred manual acceptance.

## Safety and cleanup

No shared/live database operation, environment-file edit, authentication bypass, or paid
model request was used. Temporary local OAuth-client reuse was explicitly approved and
process-local only; the frontend process tree was stopped after the user deferred browser
checks. No temporary app listener or browser tab remains. PostgreSQL used only the fixed
local disposable `_test` target; no volumes were deleted.

The feature-only publication excludes unrelated live-development working-tree changes and
generated diagnostic artifacts. Existing feature commits remain intact. Earlier gate/evaluation
files are historical, not the final verdict; the session records the final commit/push result.

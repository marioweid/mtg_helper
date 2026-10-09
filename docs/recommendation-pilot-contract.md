# Discover pilot: implementation and operating boundaries

## Now

Discover is implemented but **default off**. This is not live enablement, spending approval or
deployment. No application provider calls were made. New Cards retains its existing workflow;
Top Picks is labeled Community Picks with the same backend, source selection and caches.

The [integration plan](recommendation-live-pilot-integration-plan.md) remains the design reference.
This document describes the actual first pilot and its limitations, not a recommendation-accuracy
claim. Account enablement and the proposed spending ceilings require separate confirmation.

## Behavior

- Commander-only, eligible paper Commander nonlands. Partner/background decks and collection scopes
  are gated. Physical/planned/avoided cards are exclusions, never model support.
- Explicit goals and literal Oracle/type/keyword/mana-value constraints. Narrative preferences are
  unverified; no bracket, price, collection-ownership or combo guarantee is implemented.
- Source browsing, inspection, rules lookup, refresh and pending additions need no model calls.
- Only explicit Generate starts a background run: plan, one complete replacement revision, then
  assessment of at most 32 independently admitted cards. No eligible shortlist means no review call.
- Invalid global identities/JSON fail the review. Independently valid assessment rows survive bad
  neighbors; failed/missing/unassessed rows are not recommendations. Literal quotes are not rules
  certification. Broad searches and small samples are not exhaustive catalog coverage.
- Plan & Searches includes native rules lookup and owner-only JSON diagnostics/export. The trace
  carries actual initial/replacement searches, counts, samples, errors, raw answers and usage.
- Planning creates one pending addition idempotently, never changes physical cards. A planned cut
  conflicts rather than silently being canceled. Current source legality/color/copy limits are
  checked at planning and transactional completion, including revision completion paths.
- Origin flags survive quantity changes, normal plan merges and Oracle duplicate repair. Manual
  Cards/Rule 0 paths are not relabeled as Discover and do not acquire the flag automatically.
- Pilot feedback is isolated from legacy weights, cross-deck profiles and evaluation fixtures.

## Shared code and preserved research

Pure catalog/search/admission/evidence/rules operations and historical prompt profiles live under
`backend/src/mtg_helper/services/recommendations/`. Application modules never import `scripts.*`.
Evaluation CLIs retain their file/provider adapters, frozen pools, protocols and exclusive ledgers.
The separate `app-pilot-v1` contract uses real independent discoveries, not diagnostic fixtures.

Preserved offline suite:

```bash
cd backend
uv run --no-sync pytest -q -W error \
  tests/test_recommendation_core.py \
  tests/test_commander_discovery_luna_refined.py \
  tests/test_commander_discovery_refinement.py \
  tests/test_commander_discovery_sol_assessment.py \
  tests/test_commander_discovery_sol.py \
  tests/test_commander_discovery_run.py \
  tests/test_commander_discovery_check.py \
  tests/test_deck_recovery_check.py \
  tests/test_assistant_quality_eval.py \
  tests/test_new_cards_evidence.py
```

`.github/workflows/recommendation-core.yml` runs these offline checks without secrets, a database,
network calls or ignored research caches. Full catalog replays are separate provisioned checks.
Existing spent/stopped authorizations are never reusable, including the unknown Sol timeout.

## Sources and migrations

`db.apply_schema` adds the pilot tables and fields idempotently. It does not enable the capability.
Normal Admin card sync publishes complete normalized root/face facts alongside unchanged legacy
New Cards facts, in the same catalog transaction. Immutable compressed card/rules snapshots are
hash checked, bounded and retained in PostgreSQL. Read-only indexes cache two snapshot pairs.

The complete official rules text is packaged under
`backend/src/mtg_helper/services/recommendations/data/rules-20260925.txt`, not an ignored cache.
Its original SHA-256 is
`8d860e451f20f38865b725b42d82feb714c725373dd8f3b32b8652b3eeb070ca`.
Git attributes preserve the original rules, frozen JSON evidence and input-fixture bytes across
Windows and Linux; staged blobs were verified byte for byte before committing.
Malformed/missing optional rules prevent experimental readiness, not legacy startup/card sync.
Rules updates currently require a reviewed package/hash change and normal publication; there is no
runtime user-supplied rules URL. Card sync does not ask a model to classify capabilities.

`source_repository.prune(pool)` is explicit maintenance, not polling/startup work. It conservatively
retains every run-referenced generation, latest cards and rules, and recent unreferenced snapshots.
Historical referenced snapshots therefore do not expire in this first pilot. Missing explicitly
requested snapshots return unavailable rather than replaying against current sources.

Deleting a deck leaves its run/attempt spend records and unknown holds intact. Deleting an account
uses existing account cascade semantics; limits are account scoped, not a global identity quota.

## Provider and durable spending

The following are implemented **estimate guards**, not approved live spending or provider caps:

| Bound | First pilot |
|---|---|
| Model/profile | `gpt-5.6-luna` / `app-pilot-v1`, standard tier |
| Requests | At most 3; no application or SDK retry |
| Timeout | 300 seconds per request |
| Run reservation | 67,750 integer microdollars ($0.06775) |
| Run ceiling | 100,000 microdollars ($0.10) |
| Account/day ceiling | 1,000,000 microdollars ($1), UTC |
| Phase input bytes/output tokens | 20,000/5,000; 60,000/5,000; 95,000/10,000 |

Input reservations use $0.25/M tokens conservatively, output $1.20/M, with no assumed caching.
Rates must be rechecked before enabling. Unknown usage/model/tier or provider errors retain an
unknown hold and stop dependent stages. These holds survive UTC rollover and block new spending.
Never erase an attempted row or create a replacement authorization to bypass a hold.

Account row locks serialize reservation/settlement. A unique request key binds immutable inputs;
reusing it with different inputs is rejected. One active run/account is enforced in PostgreSQL.
Different request keys conflict while a run is active. Attempts are claimed exactly once and
committed before HTTP, with fenced 10-minute leases. Expired/restarted work is interrupted, never
resent. Late known receipts settle once, even when their worker cannot publish results anymore.
Response/request IDs are retained when available. In-memory tasks are executors, not durable state.

Unknown-billing reconciliation is intentionally not a self-service UI operation. A verified late
receipt can settle through the run repository. Otherwise an operator must establish provider billing
and obtain an explicitly reviewed reconciliation; there is no safe “clear hold and retry” button.

## API and feature gate

All endpoints require authenticated deck ownership and the `recommendations` capability, default
false, under `/api/v1/decks/{deck_id}/recommendations`:

- `GET /status`, `POST /preview-query` (literal cards and native rules, no provider request).
- `POST /runs` (explicit request key/input; 202) and `GET /runs/{run_id}`.
- `GET /runs/{run_id}/trace` (private diagnostics).
- `POST /runs/{run_id}/candidates/{oracle_id}/plan` (validated recommendation).
- `POST /candidates/{oracle_id}/plan` (explicit manual, unassessed source addition).
- `POST /runs/{run_id}/feedback` (isolated feedback).

Card cursors bind commander, query and source pair; rules continuations require the pinned rules
hash and exact terms. Polling projects persisted results and overlays current exclusions, rather
than reconstructing sources or evaluating advice. Missing sources do not disable Cards or Community
Picks. Revoking the capability stops future run stages; an in-flight request may still bill.

## Verification and remaining gates

See `backend/tests/test_recommendation_{core,pilot}.py` and the frontend Discover tests.
Database/API/SDK tests use isolated PostgreSQL and replace external HTTP only. They do not
exercise paid model behavior.

Completed checks:

- 145 offline backend checks: all 135 preserved evaluation checks plus 10 application-core checks.
- 34 real isolated PostgreSQL checks: 14 Discover, 17 legacy New Cards, 3 card-identity checks.
  Covers source-generation changes, single-use claims, unknown holds/UTC rollover, deleted-deck
  spending, late receipts, ownership, isolated feedback, current completion legality and origins
  through manual merge, Oracle repair, partial and batch completion.
- All 60 frontend tests, frontend typecheck/lint/format, backend Ruff lint/format and `ty` passed.
- Five offline historical replays preserved all 37 archived research JSON files byte for byte.
- Wheel packaging verified the complete official rules text/hash. Clean schemas were initialized
  by database tests; reapplying the schema preserved all 22 immutable test source snapshots.
- Independent boundary review found one P2: card pagination dropped its pinned rules hash. The
  repaired response/controller and fingerprint behavior passed a focused independent recheck and
  a real rules-publication regression.

The broader existing planned-change suite is **not a pass**:
`test_planned_addition_is_excluded_from_physical_deck` expects two planned Sol Rings, but singleton
clamping yields one (planned deck count 2, not 3). This exact failure was reproduced on pristine
`HEAD` (`8c1db1aa`), outside this implementation. No unrelated legacy behavior was changed to make
that assertion pass. No browser E2E or paid application-model test was performed.

Before any live pilot: confirm account-specific enablement, spending bounds, provider rates and
full-source readiness on the target deployment. New Cards migration, broader deck-aware analysis,
model comparisons and release sweeps remain separately scoped and authorized. This implementation
has not established semantic accuracy or measured real application model latency.

# Discover pilot: implementation and operating boundaries

## Now

Discover is implemented but **default off**. This is not live enablement, spending approval or
deployment. No application provider calls were made. New Cards retains its existing workflow;
Top Picks is labeled Community Picks with the same backend, source selection and caches.

The [integration plan](recommendation-live-pilot-integration-plan.md) remains the design reference.
This document describes the actual first pilot and its limitations, not a recommendation-accuracy
claim. Account enablement and the proposed spending ceilings require separate confirmation.
An optional **Draft commander strategy** action now proposes a source-only, editable goal before
card generation. It does not automatically replace a goal, save a deck or generate cards.

## Behavior

- Commander-only, eligible paper Commander nonlands. Partner/background decks and collection scopes
  are gated. Physical/planned/avoided cards are exclusions, never model support.
- Explicit goals and literal Oracle/type/keyword/mana-value constraints. Narrative preferences are
  unverified; no bracket, price, collection-ownership or combo guarantee is implemented.
- Source browsing, inspection, rules lookup, refresh and pending additions need no model calls.
- Explicit **Draft commander strategy** makes one separately bounded call using only complete
  commander facts. Review the unverified goal/explanation/uncertainties, select **Use as goal**, edit
  the goal if needed, then explicitly Generate cards. Blank or existing edited goals survive refresh;
  drafting never writes the saved deck description or discards previous card recommendations.
- Only explicit **Generate** starts the card run: plan, one complete replacement revision, then
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
`app-strategy-v1` is a one-call draft, not a discovery/assessment pool or a card recommendation.
It reuses the same run/attempt ledger, account lock and unknown holds; no schema migration or new
spending account is needed. A draft cannot authorize recommendation-origin additions.

Preserved offline suite:

```bash
cd backend
uv run --no-sync pytest -q -W error \
  tests/test_recommendation_core.py \
  tests/test_recommendation_strategy.py \
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

The optional `app-strategy-v1` draft has one `plan` attempt, a 20,000-byte framed input bound and
2,000-output-token bound. It reserves 7,400 microdollars ($0.0074), under its 10,000-microdollar
($0.01) estimate ceiling. It shares the same $1/account/UTC-day allowance, one-active-run lock and
unknown holds as card runs. Using/editing a completed draft costs nothing; a later explicit card
Generate retains its independent three-call bounds above. Neither action starts the other.

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

The Admin page has a **Discover · Experimental** access panel near the top. It loads the signed-in
account and effective capability, then offers **Enable for my account** or **Disable for my account**.
These explicit actions use the existing authenticated admin feature-flag endpoint with that account's
ID; the panel never changes the global default or other accounts. Loading/refreshing status is
read-only, and toggling access never generates recommendations. After enabling, reload an open deck
to see the Discover tab. An uncertain save requires **Refresh status** before another change.
This convenience control does not approve spending or establish source readiness/provider prices.
Disabling stops future run stages; a request already in flight may still bill.

All deck recommendation endpoints require authenticated deck ownership and the `recommendations`
capability, default false, under `/api/v1/decks/{deck_id}/recommendations`:

- `GET /status`, `POST /preview-query` (literal cards and native rules, no provider request).
- `POST /runs` (explicit card-run request key/input; 202) and `GET /runs/{run_id}`.
- `POST /strategy-drafts` (explicit request key only; 202). Status returns the latest draft in
  `strategy_run` independently of the latest card `run`. The completed run's `strategy` contains
  `goal`, `explanation` and `uncertainties`; card runs do not acquire it. Lost-response retries
  retain the same request key, and keys cannot be reused across paid profiles.
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

- 149 offline backend checks: all 135 preserved evaluation checks, 10 application-core checks and
  4 strategy-draft checks.
- 42 real isolated PostgreSQL checks: 15 Discover, 7 strategy-draft, 17 legacy New Cards and
  3 card-identity checks.
  Covers source-generation changes, single-use claims, unknown holds/UTC rollover, deleted-deck
  spending, late receipts, ownership, isolated feedback, current completion legality and origins
  through manual merge, Oracle repair, partial and batch completion.
- All 90 frontend tests (including 18 admin-access and 12 strategy-draft checks), frontend
  typecheck/lint/format, full backend Ruff lint/format and `ty check src/` passed.
  Draft checks cover separate reservations/profile fencing, duplicate workers, expiry/late settlement,
  shared daily allowance, cross-profile/UTC unknown holds, explicit goal use and no automatic deck edit.
- Five offline historical replays preserved all 37 archived research JSON files byte for byte.
- Wheel packaging verified the complete official rules text/hash. Clean schemas were initialized
  by database tests; reapplying the schema preserved all 22 immutable test source snapshots.
- Independent boundary review found one P2: card pagination dropped its pinned rules hash. The
  repaired response/controller and fingerprint behavior passed a focused independent recheck and
  a real rules-publication regression.
- Independent read-only review of the strategy-draft paid/action boundary found no supported
  blockers. It inspected profile-specific bounds/fencing, shared holds/settlement, request-key
  identity, status separation and explicit goal use; it did not independently rerun the suites or
  establish paid-model behavior/semantic correctness.

The broader existing planned-change suite is **not a pass**:
`test_planned_addition_is_excluded_from_physical_deck` expects two planned Sol Rings, but singleton
clamping yields one (planned deck count 2, not 3). This exact failure was reproduced on pristine
`HEAD` (`8c1db1aa`), outside this implementation. No unrelated legacy behavior was changed to make
that assertion pass. No browser E2E or paid application-model test was performed.

Before any live pilot: confirm account-specific enablement, spending bounds, provider rates and
full-source readiness on the target deployment. New Cards migration, broader deck-aware analysis,
model comparisons and release sweeps remain separately scoped and authorized. This implementation
has not established semantic accuracy or measured real application model latency.

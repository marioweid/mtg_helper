# Source-backed recommendations: live-pilot integration plan

## Now

**Implemented default off. No deployment, account enablement or paid application calls.**
The first commander-only adapter, shared core and isolated UI are implemented. Independent boundary
review found a rules-snapshot pagination issue, repaired and confirmed by a focused recheck. See the
[implemented contract](recommendation-pilot-contract.md) for actual boundaries and operating notes.
Live account enablement and spending authorization remain separate gates.
The user also chose **draft strategy first**: one source-only call now offers three directions with
pace, early setup/ramp, engine and possible payoff (not necessarily complete win conditions).
Review/**Use as goal**/edit then separately Generate cards; selection carries all phase context and
uncertainties into the goal. `app-strategy-v2` reuses durable spending/daily accounting without
replacing card history or changing `app-pilot-v1` bounds; its estimate ceiling remains $0.01.
Archived drafts retain traces/spending but cannot be resumed or selected under the new contract.
Results/source matches use shared image tiles with current-catalog artwork outside pinned evidence.
The user wants to live-test the new pipeline alongside the existing recommendations and keep the
research/evaluation workflow active. They explicitly chose **commander-only first**: physical cards
and planned additions are exclusions, not model support or a deck-aware balance analysis.
Luna remains the pilot baseline. Astra reviewed the draft: **feasible after changes**. The supported
findings are incorporated below; implementation checks and limitations are recorded in the contract.

This changes the earlier separation policy: an opt-in application adapter is now proposed, not a
replacement of the old system or a claim that the prototype is fully accurate. The latest six-call
Luna experiment improved literal grounding to 122/128 but retained discovery and rules errors.
[Measured evidence](research/commander-discovery-luna-refined/README.md) remains authoritative.
All previous paid authorizations are consumed; application spending limits below are proposals.

## 1. User-facing layout and scope

On `frontend/app/decks/[id]/page.tsx`:

| Tab | Behavior |
|---|---|
| Cards | Unchanged physical deck and pending-plan workspace. |
| Community Picks | Rename current Top Picks; keep its Moxfield/Archidekt logic, caches and API. |
| Discover · Experimental | New commander-only source-backed pipeline; no community admission. |
| New Cards | Existing pilot initially; shared source-backed core in phase 2. |
| Combos / History | Unchanged. |

Discovery has **Results** and **Plan & Searches** views, not a proliferation of role-based tabs.
Results separate local matches from assessed recommendations and pending/failed/uncertain cards.
Plan & Searches shows intentions, initial/revised searches, totals, zero results, explicit errors,
sampling/truncation, rules pages and provenance. Intent names remain arbitrary strategy prose.

Banner: "Commander-only experiment. Does not assess your current deck's balance or interactions.
AI advice is unverified. Nonland cards only in this first pilot." Partner commanders must either
be supported with both complete facts/combined identity and a dedicated test or explicitly marked
unavailable; do not silently use one commander. Initial release can gate unsupported partner decks.

Opening a tab, refreshing/polling, or changing a display filter performs **no model request**.
A visible Generate button previews card-run call/spend bounds and explicitly starts a run. An
optional, separately priced Draft 3 commander strategies button starts only the source-only draft;
reviewing/copying/editing its result performs no model request or saved-deck edit. Local source
browsing, card details, filtering and manual planning remain available while AI is slow or absent.
No optimistic "no matches" result when sources are absent or work is pending/failed.

Do not change builder stages, coach/chat tools, optimizer or their prompts in this first rollout.
Do not relabel their existing logic as the new engine. Keeping the legacy path is an explicit user
requirement, not a hidden fallback from failed source-backed recommendations.

## 2. Hard separation: one shared tested core, two adapters

```text
                         mtg_helper/services/recommendations/
                   source facts / typed queries / rules lookup
                  prompts+schemas / observations / evidence checks
                         deterministic candidate admission
                            /                     \
          scripts/evaluation adapter             app pilot adapter
          pinned files + single-use ledger       authenticated snapshots + durable runs
          offline replay + paid experiments       explicit budgeted requests + tabs
```

Promote reusable operations from `scripts/commander_discovery.py` and
`scripts/commander_discovery_refinement.py`, plus their pure dependencies: `Catalog` and eligibility
from `deck_recovery_check.py`, `paper_design`/card typing from `new_cards_data_spike.py`, and
`Stage`/prompts from `commander_discovery_check.py`. Leave CLI/provider/file side effects behind.
Move Luna prompt/stage definitions into a versioned profile. The core has no FastAPI, database,
secret, fixture-path or HTTP side effects. Map source `cmc`/`card_faces` into model-facing
`mana_value`/`faces`; never feed presentation facts back into the raw-source matcher.
Inject catalog/rules inputs and provider execution through the appropriate adapter.

Application code must **never import `scripts.*`**, replay receipts, require the Meren/Saheeli
fixtures, or depend on a developer's ignored `.cache` directory. Do not copy-paste a second engine.
Research still invokes the same core through CLI modules. Keep frozen prompts/schemas/source hashes
and old single-use guards intact; version new behavior and preserve old receipts unchanged.
Before promotion, all existing 135 scoped tests and old offline replays must remain equivalent and
byte-identical. If an intended improvement changes a request/schema, create a new protocol version
and record that difference; do not call it the same benchmark.

**Two distinct steps:** behavior-preserving extraction first, then a new `app-pilot-v1` protocol.
The latter supplies goals/declared constraints, real shortlists and operational checks. Do not reuse
the frozen review prompt's assertion that no budget/bracket/combo restriction was supplied.
Historical Meren empty-plan recovery remains replayable; rejection below is new app behavior.

### Required pilot hardening, not a promise of semantic accuracy

- Reject a fully empty/unexecutable plan despite valid JSON; retain raw output and readable failure.
  At least one valid executable search or resolved eligible nomination is necessary to proceed.
- Keep the one-revision replacement policy; do not union dropped candidates to inflate admission.
- Execute final queries before assessment and expose zero/error/broad results. No silent extra paid
  revision to fix them. Usable candidates may be assessed with incomplete-discovery warnings.
- Keep exact candidate IDs, complete-coverage schemas and duplicate-key rejection. The old parser
  rejects missing/schema-invalid rows globally; preserve that benchmark behavior. In the new app
  protocol, valid JSON with unambiguous known IDs can yield individually schema/evidence-validated
  rows; absent/invalid rows stay failed, never repaired or rejected fits. Invalid JSON, duplicate
  properties or ambiguous/extra identities fail the response globally. No automatic repair call.
- Render mana costs/body/source facts from authoritative fields, separately from generated advice.
- Keep literal evidence validation initially. Field/paragraph-bound citations are a later versioned
  improvement, not a way to declare old failed quotes valid. No rules-engine prerequisite.

## 3. Source adapter: prerequisites and ingestion

Do **not** reuse `mtg_card_search.py` or `retrieval_service.py` as admission engines: they contain
community restrictions, popularity ordering and heuristic roles. No embeddings or semantic tags.
Do not reuse existing `/cards/search` as though it supports the experiment's full typed contract.

The ordinary `cards` table lacks full faces/layout. The existing `new_card_catalog` actually stores
facts for the broad catalog, but its `CardFacts` omits mana value, keywords and paper eligibility;
its face normalizer also constructs flattened root text. It is not yet the experiment's source
contract. Neither legacy text truncation nor a join that reconstructs missing faces is acceptable.

Prefer **an additive `source_facts` JSONB field on the existing catalog**, populated by the same
atomic Scryfall publication, with a versioned canonical source model. Preserve the existing `facts`
field for the old New Cards pilot until its migration. Avoid unnecessary whole-catalog duplication.
Canonical facts include Oracle ID, intact top-level Oracle text, every printed face and cost,
mana value, types, arbitrary keyword strings, layout, color identity, legality, games/paper facts,
relevant eligibility fields, and source generation/hash. Missing values remain unknown, not zero.
The source model is facts, **not per-card semantic capabilities**.

Rules: deploy the complete versioned official text as a separately hash-checked resource, not the
nine diagnostic excerpts or workstation cache. Startup/readiness loads it locally. Source updates
are explicit/admin-controlled with bounded trusted-host fetching, validation and atomic last-good
publication. Tab opening never syncs. Show source date/hash; unknown mechanics stay uncertain.

The current catalog overwrites each Oracle identity: adding `source_facts` alone does not retain
historical generations. Add **immutable, content-addressed source snapshots in PostgreSQL**: bounded
compressed normalized card/rules payloads and a version/hash manifest, inserted before/with catalog
publication. Runs reference their exact snapshot hashes. This supplies all workers after restart
without a new storage service or dependency on a workstation volume. Compression/index building
happens off the event loop, outside the publication transaction's expensive preparation phase.

A cached read-only index for each pinned generation executes the pure literal matcher. Never scan
or rebuild the whole catalog per poll. Query previews/pagination bind to snapshot hash, query
fingerprint, ordering/seed and cursor version; incompatible cursors fail explicitly. Test across
workers and a sync during a run. Source/advice history is separate from live action revalidation.

Retain latest sources, every active/unresolved-billing run's sources, and terminal-run sources for
at least 30 days after completion. Prune only unreferenced expired snapshots with an explicit
maintenance action; never cascade-delete run/attempt history. Archived candidate facts/results
remain readable afterward, but expired full-catalog query replay returns source-unavailable/410,
not silently the current catalog. Missing/corrupt sources disable the experiment, not app startup.

## 4. App workflow and candidate policy

```text
explicit user action + commander(s) + editable goal + declared constraints
   -> pin source/rules/profile and exclusion snapshot
   -> initial Luna plan
   -> actual local card/rules observations
   -> one Luna replacement revision
   -> execute final queries; publish immediate local matches
   -> select bounded real shortlist (no forced diagnostics or old frozen review pools)
   -> one Luna contextual assessment of that shortlist
   -> source evidence + unverified advice + explicit user planning
```

Unlike the research comparisons, app assessment uses **its real independent discoveries**.
Start with the tested independent-shortlist bound of **32 distinct eligible nonlands**, interleaving
nomination and query channels. Preserve counts and provenance for thousands of unadmitted matches;
a 32-card assessment does not represent catalog coverage. No promise of comprehensive synergy.
If nothing is eligible/usable, stop without paying for an empty assessment.

Commander identity/legality and supported deterministic constraints are enforced in code. Narrative
strategy preferences remain unverified advice, not guaranteed semantic/combo filters. Unsupported
hard restrictions return an explicit error, never a weaker approximation. Physical deck cards,
already planned additions, explicit avoided cards and run exclusions are not admitted to the
addition shortlist. They never become support facts in this commander-only mode. Source-query
previews and the source browser remain inspectable independently of this addition exclusion view.
If a user filters by price/ownership, enforce it as a declared candidate constraint, include it in
the context hash and report unknown prices separately; do not silently treat unknown prices as free.
No bracket/budget/combo guarantees are inferred from an absent constraint or the commander's name.

Initial MVP goal is explicit text, seeded from deck description only if visible/editable. Do not
silently pass cached coach memories or legacy theme scores as authoritative strategic instructions.
All user/source strings are untrusted data in model prompts; returned text is rendered as text.

## 5. Durable execution, spending, privacy and invalidation

Reuse existing PostgreSQL lease/ownership patterns, not the in-memory optimizer job registry.
Propose additive `recommendation_runs`, `recommendation_attempts` and account spending reservations.
Store immutable input snapshots, model/profile/schema versions, source/rules hashes, exclusions,
query executions, candidate provenance, per-card validation status, raw bounded outputs, returned
usage/tier, known estimate and unknown-billing state. Bind every run/attempt to account + deck.
No secrets or public logs containing full private inputs; owner-only diagnostic/export access.

- One active paid run per account. Duplicate same-deck/fingerprint clicks return its ID; another
  deck or different inputs get a clear conflict. Request-key reuse with different input is rejected.
- Atomically reserve conservative spend before accepting work; checkpoint each attempt before HTTP.
  Budget arithmetic uses integer microdollars/checked usage, not unguarded float comparisons.
- Each stage transitions `pending -> attempted -> completed/failed/unknown` through a single-use
  transactional claim that verifies current fenced lease, prerequisite and remaining reservation.
  Commit the attempted checkpoint before HTTP. Only its successful claimant may send; an expired
  worker cannot begin another stage. Never reclaim/reissue an attempted stage. Existing New Cards
  leases guard publication only and are **not sufficient** to copy as paid-execution protection.
- **Proposed pilot bounds:** Luna standard tier, low reasoning/verbosity, `store=False`, no retries;
  at most **3 calls/run**, input/output bounds 20 KB/5k, 60 KB/5k, 95 KB/10k; **300 s/call**.
  At previously checked rates this reserves **$0.06775/run**, within a proposed **$0.10/run cap**.
  Proposed account daily ceiling **$1 for this new engine only**, using known spend plus holds.
  The existing New Cards pilot has a separate 30-batch quota and is outside this dollar ceiling.
  Recheck standard-tier prices before implementation/enablement; estimates are not provider caps.
- Publish background progress; do not hold a web request through the multi-call sequence.
  BackgroundTasks may execute the pilot, but PostgreSQL owns state. A restart marks interrupted
  work, never automatically reissues an attempted request. No new queue framework is necessary.
- Use a fenced token and per-stage lease renewed before each paid request, longer than the 300 s
  timeout plus persistence margin (proposed 10 min). Expired work is interrupted, not reclaimed
  for automatic paid retry. Preserve returned attempt receipts even if publication is fenced out.
- Timeouts/missing usage/unexpected model or tier freeze remaining work and keep the unknown attempt
  reservation. New-engine spending does not bypass an unresolved account hold. Explicit admin
  reconciliation/new authorization is needed; unknown billing is never zero. Never-attempted stages
  release their reservations on termination; attempted unknown stages retain their full hold.
  Known late receipts settle the attempt idempotently even if result publication is fenced out.
  Process death after checkpoint but before proven receipt remains conservatively unknown.
  Daily UTC rollover resets only settled daily totals; unresolved holds survive the date boundary.
- Poll persisted progress/results, not source scans or deck-context reconstruction.
  Navigation does not cancel/restart work. No automatic analysis from changed filters or plans.

Fingerprint commander(s), goal, constraints/exclusions, catalog/rules hashes, profile/model/schema
versions and sample seed. A changed physical deck affects exclusions, not support semantics; a
changed goal or commander invalidates strategic analysis. Preserve prior runs with explicit stale
labels; do not overwrite an active snapshot. Separate strategic staleness from exclusion changes:
planning one suggestion hides that identity without forcing regeneration for every remaining card.
New runs require explicit Generate. Revalidate current ownership, source legality/color/copy limits
at action time despite cached/run snapshots.

## 6. Proposed API and action boundaries

Under `/api/v1/decks/{deck_id}/recommendations` (all DataResponse/ErrorResponse envelopes):

- `GET /status`: readiness/current run summary; no model/source sync.
- `POST /preview-query`: typed local card/rule query preview; no model charge.
- `GET /candidates`: stable paginated source matches/status filters for a run/snapshot.
- `POST /runs`: explicit goal/constraints + client request key; reserve and return 202/run ID.
- `GET /runs/{run_id}`: ownership-scoped progress, counts and valid cached advice.
- `GET /runs/{run_id}/trace`: owner-only sanitized detailed inputs/queries/evidence/usage.
- `POST /runs/{run_id}/candidates/{oracle_id}/plan`: idempotent guarded recommendation-origin plan.
- `POST /runs/{run_id}/feedback`: useful/incorrect/uncertain/manual note; not cross-engine scoring.

Run IDs alone never grant access: check owner/account/deck association on every read/action.
The new planner must lock/revalidate before writing a pending addition through the existing planning
invariants; never a direct physical `deck_cards` write. Preserve recommendation origin so completion
also rechecks legality/copy limits (existing `new_cards_origin` only covers the old pilot).
Generic `create_plan` alone is insufficient: it checks color/copies but not source legality or
recommendation freshness. Do not loosen legacy/manual Rule 0 behavior for this integration.
Recommendation-origin planning can be disabled for invalid/stale advice; independent manual source
browsing/planning remains possible with clearly separate labels and existing explicit workflow.

The public single-plan endpoint in `routers/decks.py` already goes through
`services/revision_service.py::apply_revision`; single/batch guards must support the new origin.
Preserve origin through merges/quantity changes/partial completion and
`services/oracle_duplicate_repair_service.py` delete/recreate repairs, not only the initial insert.
Test collection-backed additions, commander/legality changes and whole-transaction rollback.
Do not wire the pilot through the older unguarded `planned_change_service.complete_plan()`.
Current New Cards planning is `new_cards/service.py::plan`; there is no `new_cards/planning.py`.

Pilot feedback uses its own run-scoped records, **not `deck_feedback`**, which feeds existing AI
weights and cross-deck profile aggregation. Add a non-interference test. Feedback is not implicitly
added to model prompts, other decks, or clean holdouts.

## 7. New Cards phase 2: same core, different admission

Do not relabel the current pilot as the new engine before replacing its adapter and testing it.
Phase 2 is a separate proposed **commander-only** release-discovery mode, not current-deck fit.
It replaces the old evaluator/claim path and context contract: only commander/goal/declared
constraints enter assessment; physical/planned cards are exclusions, never support. The existing
physical-deck pilot remains unchanged until this transition is separately approved, visibly labeled
and tested. Stop using old cached judgments as new judgments; retain their history. Do not reuse
`new_cards/repository.py::_context()` or the existing panel's current-deck fit claims.

Define an immutable release scope ID from dates/window, eligibility policy, source/rules versions,
commander/goal/constraints and snapshot. Declare **separate bounded per-batch authorization and
reservations** for continuation; Discover's three-call ceiling does not authorize release traversal.
Cached plan reuse requires identical strategic/profile/rules context; mismatches require an explicit
new bounded planning action. Exclude lands until a land-aware contract is approved.

Declare a release scope/window and eligible snapshot; **enumerate all eligible Oracle identities**
before strategic selection. Query matches may organize/explain candidates, not exclude releases.
Assess bounded batches explicitly (initially eight), reusing cached commander plan/rules context.
Show pending, failed, uncertain, rejected and accepted source cards with coverage counts. Do not
claim "no matches" before the scope is fully handled; per-item failures do not fail valid neighbors.
Batch continuation may reuse a valid plan, but retries of failed/unknown-billed attempts require an
explicit bounded action; never automatic retry from polling. Special-product/source coverage gaps
must be disclosed. Clarify/test land eligibility separately from the nonland Discover MVP.
This release enumeration/context caching is new behavior, not proven by the current 64-card tests.

## 8. Implementation order and acceptance gates

1. **Core extraction + replay parity.** No UI/database changes. Existing 135 offline checks, byte-
   identical frozen replays, new module-dependency check (app never imports scripts), operational
   empty-plan tests, per-row quote failure and unrestricted keyword/face/query contract tests.
2. **Source/rules readiness.** Additive schema/source publishing, no destructive migration. Verify
   last-good rollback on ingest failure, all faces/printed costs/paper legality, partner gates,
   literal `%`/`_`, invalid ranges, repeated-symbol presence limits and stable identity pagination.
   Apply/test on both an existing DB and a clean DB using repo `apply_schema` startup behavior.
3. **Run service.** Persistent leases/budgets, fence/checkpoint tests, account isolation,
   duplicate clicks/key mismatch, cross-deck conflicts, single-use stage claims, UTC rollover,
   late receipts, restart/expiry/timeout/unknown prices and fast polling. Source/cursor reload works
   across workers and concurrent publication; no extra paid call from a fenced worker.
   Only network I/O is mocked. Backend experimental gates land with routes, not after UI enablement.
   Independent trust-boundary/migration review before use.
4. **Discover UI + legacy rename.** Isolated component/controller; no extra paid auto-load effects.
   Source browse remains usable during slow/error runs, filters/paging don't re-run AI, valid cards
   survive one bad result, source/advice visually separate, stale state and explicit actions.
   Legacy Top Picks calls its original service with unchanged source selection/cache behavior.
   Test plan idempotency, action-time validation, no physical mutation and origin completion.
5. **Opt-in live pilot.** Add an account-level experimental capability using existing feature flags;
   default off, enable only the requested test account. Backend gates routes as well as UI. Confirm
   budget proposals and enablement separately. Export bounded sanitized traces to new eval fixtures
   only by explicit owner action. Do not automatically export private deck/goals to repository/docs.
6. **New Cards adapter**, after Discover pilot acceptance; then unused strategy/release sweeps.
   Current-deck-aware builder/coach integration and broader model comparison remain separate work.

Run relevant backend pytest checks with warnings-as-errors, Ruff lint/format and `ty`; frontend
Vitest, `pnpm typecheck`, `pnpm lint` and `pnpm format:check`. Add an offline CI job for the shared
core using small committed card/rules fixtures, no secrets/network/ignored cache prerequisites.
Full-source archived replay remains a separate hash-checked check with explicitly provisioned
snapshots; unavailable sources are not reported as a pass. Preserve the existing evaluation CLI
entry points, paid ledgers and the 135-check suite alongside new app contract tests.

Live traces and user feedback supplement, not replace, deterministic and offline research tests.
Mark discussed/live-tested strategies as regressions; preserve genuinely untouched holdouts.
No hidden diagnostic pool/model hints in the app, no silent semantic filters, no false certainty.

## Astra review

Read-only review by **openai-codex / gpt-6-astra**: **feasible after changes**, not supported as the
original draft stood. Incorporated five supported findings: durable generation retention; single-use
paid-stage claims/reservation settlement; origin preservation across revision/repair paths; complete
pure extraction and a separate app protocol; explicit commander-only/bounded New Cards migration.
Also incorporated isolated feedback, exclusion-vs-strategy staleness and nonfatal source readiness.
The owner inspected affected paths before accepting these changes. No second full review is claimed.

Review did not rerun the earlier 135 offline checks or certify Magic advice, billing, application/DB
behavior or migrations. This turn checks document links, reservation arithmetic and diff whitespace.
Docker/real database availability remains an implementation gate. No application files or receipts
were changed; no application paid calls, deployment, migration or enablement occurred.

**Next:** approve the Discover implementation scope (steps 1–4), then implement/test it behind the
existing default-off capability. Live account enablement/spending and New Cards migration require
separate explicit confirmation; no leftover experiment budget may be reused.

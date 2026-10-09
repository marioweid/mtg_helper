# Interactive brewing: vision and proof before rollout

## Now

**Status: commander-only Discover implementation requested; default off, not a proven recommender.**

The user now wants to live-test the source-backed pipeline alongside the old Top Picks logic, kept
as Community Picks, while retaining the evaluation tools. They chose commander-only first, with
physical/planned cards as exclusions rather than support. The
[live-pilot integration plan](recommendation-live-pilot-integration-plan.md) proposes a separate
Discover tab and later New Cards migration. Astra found the draft feasible after changes; source
retention, spending/lease transitions, plan-origin preservation and app/eval contract separation were
incorporated. The shared core and isolated adapter are implemented and independently reviewed; see the
[implemented contract](recommendation-pilot-contract.md). No deployment, account enablement or paid
application calls occurred. Model defaults and experiment receipts remain unchanged; old paid
budgets stay consumed. Semantic accuracy and real application latency remain unproven.

The user wants interactive visual building and goal-driven agent advice without depending on
Moxfield, EDHREC, or embeddings. Evaluation decks are Zaxara, Camellia, Yuna Grand Summoner, and
Meren. The user subsequently supplied complete Yuna and Meren lists for an initial recovery test;
Zaxara/Camellia lists and explicit constraints remain outstanding. Raw fixtures are preserved under
`backend/evals/deck_recovery/`. The user prefers practical recovery evidence before building a UI,
not the full acceptance matrix as a prerequisite.

An independent, read-only Astra architecture challenge covered clean commit `8c1db1aa`.
The parent inspected the active paths and verified the context/search findings below. Astra
recommended a local-first workspace with bounded AI enrichment; the parent accepts that correction
rather than putting an AI service on every interaction's critical path.

At the earlier recovery checkpoint, no application feature code, production data, model defaults
or deployment changed. The user separately approved and completed a four-call Luna/Terra recovery smoke test using hidden answer
lists: Yuna recovered 15/16 of 65 targets and Meren 19/19 of 66, from 50 suggestions per run. The
20-30-hit signal was not reached. Estimated API cost was $0.05961; all four calls completed with no
retries. [Measured report](research/deck-recovery-smoke/README.md) records outputs and limitations.
Evaluator code/fixtures/tests were added, not a UI or shared production recommender. Both the old
research budgets and that four-call authorization are exhausted. A separately authorized
source-grounded discovery test is now complete (below); further paid checks need new permission. After inspecting all outputs, the user judged
the recommendations a solid base and preferred Terra, citing Meren's reanimation versus cast-based
draw as an important fit distinction. Exact recovery is not their sole acceptance criterion. Their
remaining requirement is casual browsing and discovery of model-unfamiliar releases. The broader
interaction trial remains a later proposal, not the immediate implementation plan.

**Architecture rethink:** the user rejected universal cached capability extraction because a fixed
interaction schema cannot represent Magic's breadth. A second read-only Astra opinion agrees.
Retract that approach; prefer deck-specific runtime query plans over raw source facts, followed by
contextual model assessment. A small typed query interface is not an interaction ontology. For a
small New Cards pool, prefer complete enumeration over semantic admission filters. No new
application calls or implementation occurred in this rethink. Yuna/Meren are now regression cases,
not untouched holdouts; next proof must include pip/devotion, cascade/casting-cost, and another
strategy that did not guide development. The user also judged the Meren/Saheeli planning examples
promising and agreed the direction is on track. These are illustrative, source-backed parent
analyses, not measured Terra planning outputs or authorization for new calls/implementation.
Saheeli is now a discussed regression case too, not an untouched holdout.

**Source-backed test completed:** the user explicitly authorized Meren/Saheeli × Luna/Terra,
up to eight requests (four plans, local retrieval, four same-pool assessments), no retries, $1
estimated ceiling. All eight completed for $0.33604205; that authorization is now exhausted.
[Measured report and actual outputs](research/commander-discovery-smoke/README.md) preserve the
frozen setup, call guard review, provenance and limitations. Both planners missed proliferate for
Meren; assessment recognized it after candidate facts and explicit rules were provided. Terra's
query genuinely found Drivnod and a post-cutoff Shuri design, but its Saheeli ETB wording returned
zero matches. Quotation/ID conformance failed and Luna made supported cost/copy/trigger mistakes.
This supports continued bounded investigation, not automatic rollout or a production model switch.
Next improve query feedback, source-language grounding and planning-time rule access rather than
hardcoding commander synergies. Scoped checks and 82 offline tests passed. No UI/production changes.

**Sol extension stopped partially:** the user separately authorized four Sol requests, no retries,
$1 estimated cap. Two plans completed; the third request (Meren assessment) timed out at the
120-second client limit with unknown usage/billing. The guard stopped before Saheeli assessment,
with no retry. Known completed-plan cost is $0.03234, **not** the unknown total cost. Sol genuinely
planned Sundial/populate retention and used working `enters` searches, but still omitted Meren
proliferate. No assessment-quality comparison is possible. [Partial report](research/commander-discovery-sol/README.md)
preserves all three attempts and fixed inputs; do not delete/resume that single-use ledger.
The user then explicitly authorized two **additional** assessment requests, $0.60 additional cap,
300-second timeout, no automatic retries. Both completed for $0.2423375; known completed Sol calls
cost $0.2746775, but whole-Sol total remains unknown because of the original timeout. Meren passed
64/64 grounding/identity checks; Saheeli had 61/64, a duplicate Wheel assessment and missing Torpor
Orb. Sol explains copy refunds, independent copies/delayed sacrifice, counter and legend restrictions
more clearly in targeted inspection, at roughly 152 seconds per review. This supports stronger
fact-fed-advisor performance, not complete coverage or a production switch. [Completed comparison](research/commander-discovery-sol-assessment/README.md)
has actual ranked outputs. Checks now cover 104 offline tests; all prior JSON remains unchanged.

**Refinement boundary:** the user approved improving the experimental pipeline while keeping it
separate from the application until testing establishes a grounded base. After clarification, Luna
(the cheapest measured model) is the refinement baseline; Sol/Terra should later use the same frozen
improved pipeline. This is pipeline/prompt refinement, not model weight training. New offline helpers
close candidate IDs/coverage, reject duplicate JSON properties, expose query observations and enable
literal planning-time lookup across the full pinned rules/glossary source. The offline preview replays
old Luna plans; it is not new model output or measured improvement. [Scope and next experiment](research/commander-discovery-refinement/README.md)
preserve the boundary. No new paid request occurred; all old live budgets remain consumed/stopped.
**Luna refined run completed:** the user approved six fresh calls with a $0.25 estimated cap,
300-second timeout, no retries and unknown-billing stop. Initial plan → source observations → one
replacement revision → assessment completed for Meren/Saheeli at $0.03395705; permission is consumed.
The original 64 candidate facts per case were preserved; additional planning/rules context and the
closed output schema mean this is a composite-pipeline test, not a single-variable ablation.
Grounding rose from 116/128 to 122/128, with every candidate assessed once, but neither review fully
validated. Saheeli used rule continuation pages and fixed a zero-result entry search; Meren's initial
schema-valid nonsense/empty operations were only recovered by revision, which still missed
proliferate and introduced two zero-result entry queries. Sai's draw cost, Second Harvest's green
payment, Doubling Season/experience and token bounce/re-entry errors remain in targeted inspection.
[Measured outputs and limitations](research/commander-discovery-luna-refined/README.md) preserve all
six requests/responses and before/after admission. 135 scoped offline tests passed; old JSON was
byte-identical after replay. No production code/model/data or deployment changed. Next refine
operational plan validation, final-query feedback, admission and source-bound citations before
another model comparison; unused-strategy and complete-release checks remain outstanding.

The reported empty New Cards feed and lag remain unreproduced. Docker was unavailable locally.
Investigating those problems is separate work, not something this proposed redesign proves fixed.

## Product decision

**Immediate local browsing and explicit deck editing; asynchronous AI advice when requested.**
Visual controls and the agent use the same deck context, discovery tools, and action validation.
They do not need the same prompt or candidate scope. New Cards adds a release-pool restriction.

The workspace stays useful if the model is slow or unavailable. Local matches are labeled as search
results, not certified fits. AI can explain, prioritize, and suggest alternatives without owning
ordinary filtering, inspection, or accepting/rejecting cards.

```text
Editable goal + current deck + selected plans + constraints
    -> authorized physical/projected snapshot
    -> community-independent candidate discovery
    -> immediate local search results
    -> optional bounded AI assessment and explanation
    -> recommendations with support, prerequisites, and tradeoffs
    -> explicit user action, revalidated against current state
```

This is a preferred hypothesis. Whether AI meaningfully improves useful recommendations at
acceptable latency and cost must be measured before replacing existing product paths.

## Required mechanism

### One visible strategy brief

Reuse existing description/memory where practical. Keep the chosen direction, constraints,
protected cards, and current task visible and editable. Separate explicit user requirements from
model assumptions. Chat may propose a brief change; it must not silently persist a new strategy.
A direction change supersedes old assumptions rather than accumulating contradictory instructions.
The experiment can use fixture-backed briefs; it needs no new production schema.

### Explicit support context

- **Physical:** actual cards, commander/partner, and quantities.
- **Projected:** physical cards minus selected cuts plus selected additions, with quantities.
- **Owned:** inventory availability, not evidence that a card is in the deck.

Show which context advice uses. Planned cards may support projected advice, never silently support
physical advice. A hypothetical package is not an accepted plan. Cold-start brewing must work with
only a commander/partner and goal, without pretending the necessary engine is already present.

Recommendations have three distinct meanings:

- **Works now:** useful with support in the selected context.
- **Utility:** independently helps a stated role or structural need.
- **Build toward:** conditional option with named missing support and opportunity cost.

A standalone utility card does not require an artificial supporting-card quotation. Build-around
advice must not be rejected solely because an incomplete list lacks its future support.

### Discovery before judgment

Use complementary, bounded channels:

1. Model-proposed names, resolved to local canonical identities and exact facts.
2. Deck-specific typed local queries over rules text, mana costs, types, and source characteristics;
   functional lane names are search hypotheses, not universal card classifications.
3. Diversified local exploration to reduce query tunnel vision.
4. For New Cards, enumeration of the eligible release pool, including model-unfamiliar designs.

Do not silently substitute a fuzzy name match. Models do not generate executable SQL. Record
candidate provenance, queries, truncation, failed lookups, and unexamined pool coverage.
Ranking cannot recover a candidate that discovery never supplies.

For this experiment, community independence means no community requests, membership gates,
inclusion scores, EDHREC ordering, community-derived fit/curve evidence, or untraced community tags
in admission, ranking, or model context. Use source rules/characteristics and independently derived
local facts. Merely disabling network access or a popularity weight is insufficient. This does not
claim that the pretrained model's learned card knowledge is independent of community material.

### Runtime query plans, not a universal interaction schema

Store authoritative source facts, not a closed vocabulary of AI-derived card capabilities. The
model proposes several searches from the commander, goal, selected deck, and examples. The query
interface describes generic executable operations: comparisons, text/keyword matching, types,
printed mana symbols/counts, and combinations. It does not encode every interaction. Existing
cost-symbol presence filters cannot represent repeated pips; any count operator needs deliberate
handling of faces/hybrid symbols and tests before claiming devotion support.

Combine model-nominated names, structural/text searches, lexical examples, separately generated
complement searches, and resumable exploration. Expansion must consider modifiers of resources,
events, thresholds, and timing, not merely repeat the commander's words. The user's Meren example
is a regression: Meren grants experience counters to the player; proliferate can increase existing
player counters. Terra nominated Yawgmoth but explained only sacrifice/draw/control, not this link.
A rules-backed proliferate search can also discover Cankerbloom and Evolution Sage. Do not encode
this as a bespoke Meren rule or a permanent capability label. Test whether general planning and
fact-fed assessment surface secondary connections; neither is guaranteed to do so.

Saheeli, Radiant Creator is now another worked illustration, not an untouched holdout or a paid
Terra result. Her plan must separate cast-based energy generation from token entry, find useful
entry/death copy targets among all eligible permanents, and explore player-counter modification
and delayed-sacrifice interactions. Whirler Virtuoso's entry can refund a copy's three-energy cost;
Solemn Simulacrum and Wurmcoil Engine reward the copy entering/dying. Proliferate can increase
existing energy; Doubling Season's counter clause concerns permanents, not energy on players.
Independent token copies do not inherit Saheeli's separate delayed sacrifice, while Sundial
requires waiting for that sacrifice trigger rather than skipping the end step in advance. These
are source/rules-backed example judgments, not proof that the proposed planner discovers them.

Deduplicate by Oracle identity, retain provenance,
and prevent a single query from consuming the entire candidate budget. Keep matching totals and
truncation visible; stable cursors must not repeatedly sample the same early/popular rows.
Queries generate candidates, not proof of fit. Assess supplied facts against this deck and goal,
with open-ended strategic explanations. Unknown rules need bounded authoritative lookup where
available, otherwise explicit uncertainty. Cache contextual judgments, not permanent semantic roles.

For New Cards, enumerate every eligible identity in the declared release scope and assess in
bounded, resumable batches. Every identity remains assessed, pending, or failed; unassessed cards
stay browsable. Enumeration removes query-admission blind spots only if traversal completes. It
does not remove model false negatives or guarantee discovery of multi-card packages. Exhaustive
assessment of the full catalog is not an interactive default until cost/latency are measured.

The current typed SQL and single-agent shell are suitable foundations, but community gates,
popularity ordering, bounded top-20 search results, and truncated/pip-incomplete context are not a
complete solution. Do not execute model-generated SQL or silently approximate unsupported searches.
No embeddings, Scryfall-syntax compiler, formal rules engine, or new framework is a prerequisite;
consider them only if evidence identifies an unmet need.

### Structured advice and safe actions

Each displayed advice item identifies a grounded card, role, fit category, concise reason,
support/prerequisites, caveat, and optional replacement. Display numeric card characteristics from
source facts, not generated prose. Do not invent calibrated confidence or win-rate scores.

Code enforces ownership, identity, legality, combined commander color identity, copy limits,
explicit exclusions, and known-price constraints. Unknown prices do not count as zero. Strategic
fit, full interaction correctness, and absence of all infinite combos are not certified by these
checks. Exact quotations establish provenance, not that the model interpreted the rules correctly.

Acceptance/planning is explicit and transactionally revalidated. No automatic physical changes.
Keep existing Rule 0/manual workflows outside the experimental recommender's strict eligibility
scope rather than silently changing their authorization or behavior.

### Two speeds and version-bound results

Filtering, card inspection, accepting/rejecting, and planning do not start another model run.
Use a cached candidate board and stable snapshot pagination rather than offsets into a pool whose
exclusions change underneath it. Distinguish a direction-specific rejection from permanent avoidance.

AI runs explicitly in bounded background jobs. Bind results to owner, support mode, deck/plans,
brief, constraints, source facts, model, and evaluator version. Superseded jobs cannot publish as
current; discard or label old results. Refiltering eligibility does not establish that old fit
reasoning is still valid. Do not hide context changes behind a cache.

Specify interruption/restart behavior. A PostgreSQL lease prevents duplicate ownership; it does
not by itself resume execution after a process crash. The experiment must show interruption and
explicit retry without introducing a new distributed-job framework prematurely.

## Repository evidence and reuse

Backend paths below are relative to `backend/src/mtg_helper/`.

| Existing path | Finding and implication |
| --- | --- |
| `mtg_assistant.py`, `commander_coach/orchestrator.py` | Already a single bounded, tool-using agent. Reuse its shell; do not revive the historical specialist pipeline. |
| `mtg_card_search.py` | Active assistant search initially restricts to hub IDs when evidence exists, supplements before truncation, and still uses EDHREC ordering. Its typed filters are reusable, its candidate policy is not community-independent. |
| `retrieval_service.py:_fetch_inclusion_signals` | Builder retrieval can call Moxfield `get_or_refresh` during the request. Local SQL alone does not describe the full runtime path. |
| `deck_fit_service.py` | Community-derived fit scores feed assistant context. Removing search requests alone leaves this influence in place. |
| `ai_service.py:build_stage`, `suggest_cards` | These load decks without `account_id` and pass primary-commander colors to retrieval. `deck_service._planned_state` omits plans without account context; partner union is available elsewhere. Align context before reusing these paths. |
| `card_search_tool.py` | A separate search orders by EDHREC rank, omits a Commander-legality predicate, and treats unknown price as zero in its cap filter. Do not reuse it wholesale as the safety boundary. |
| `commander_coach/pipeline.py`, `synergy_scoring.py` | Some diagnostics/scoring have Food/Squirrel and X/Hydra branches. Success on Camellia/Zaxara alone is not generalization evidence. |
| `frontend/app/decks/[id]/build/page.tsx` | Fetches 80 cards per request and preloads theme tabs; stage responses lack a generation guard. Measure fan-out/stale responses, but do not call these the proven cause of lag. |
| `new_cards/service.py`, `repository.py`, `evaluator.py` | Eight release/name-ordered candidates, exact-context invalidation, whole-batch quotation failure, and physical-support requirements can yield empty/churning results. Different failure/coverage states must remain explicit. |
| `commander_coach/jobs.py`, New Cards jobs | Coach execution is in-memory; New Cards leases use PostgreSQL with execution in `BackgroundTasks`. Neither is a complete durable-execution system. |

Reuse identity/copy-limit helpers, face-aware source facts, suitable typed search filters,
owner-scoped publication checks, short-key identity binding, explicit plans/revision transactions,
and the New Cards UI sequence guard. Establish a source-independent experimental context instead
of inheriting unverified community-derived fields.

Do not replace production builder, assistant, or New Cards until the slice passes. If rollout is
approved, migrate one consumer at a time and remove its replaced path rather than retain dual
recommendation engines indefinitely.

## What the existing evidence proves

The preserved [v2 experiment](research/new-cards-spike-2026-10-05/quality-v2-report.md) improved
identity binding, but only 5/8 whole responses passed its evidence contract; valid explanations
still contained rules errors.

The [v3 comparison](research/new-cards-spike-2026-10-05/quality-v3-report.md) retained 3/32 and 2/32
flagged factual-error judgments at low/high reasoning. Median latency was approximately 17.5/93.1
seconds. These selected synthetic cases do not establish general semantic accuracy or discovery
recall. More reasoning alone was not a demonstrated solution.

Current-session offline check:

```bash
cd backend
uv run --no-sync pytest -q -W error \
  tests/test_assistant_quality_eval.py tests/test_new_cards_evidence.py
```

Result: **41 passed in 0.14s**. No database or live model requests were needed. The assistant quality
harness currently checks corpus shape, phrases, and tool calls; it is not a live utility benchmark.
Passing these tests is evidence for existing guardrails, not for the proposed recommendation quality.

## First gate: simple deck recovery before UI implementation

The user accepts partial evidence: recovering 20-30 nonlands from their own good lists is a useful
first signal. Preserve the full lists as evaluator-only answer sets, not recommender input.

Proposed first run: 50 ranked, unique nonland recommendations per commander, given only exact
commander facts and an openly stated, short strategy brief. The briefs inferred from the supplied
lists are Yuna counter growth/redistribution with creature-based acceleration, and Meren sacrifice
and creature-recursion value with repeatable ETB/death effects. These are not added combo, power,
or budget restrictions. Commander-only results would be a different test and should be labeled so.

Count exact Oracle-identity hits, top-ten hits, off-list alternatives, invalid/duplicate outputs,
and source-resolution failures. Exclude commanders and sideboards. Use spell-front MDFCs as
nonlands and exclude Dryad Arbor as a land. Report 20 hits as promising and 30 as stronger initial
evidence at this fixed suggestion count; do not inflate the pool until a target is reached.
Inspect engine-specific hits as well as staples. Good off-list suggestions are not automatically
bad, but should not be counted as exact recovery. Preserve incomplete/provider-failed runs.

A first direct-prompt run measures model knowledge and goal understanding, not the complete proposed
hybrid algorithm. If it succeeds, test local resolution/search and then interactive updates in small
steps. If it fails, diagnose model/context/discovery before writing a product feature. No new paid
calls are authorized by the historical experiment budgets. See the fixture README for boundaries.

## Later interaction experiment — only after the recovery check

### Scope

One experimental **next five cards** workspace using existing UI/action plumbing and the assistant
shell. Include an editable task, physical/projected context, direction changes, explicit planning,
and a recent-pool restriction. No full builder rewrite, model-framework migration, or broad schema
migration. First exercise lifecycle and actions with replayed/mock outputs; then perform only the
separately authorized live comparison.

### Fixtures and holdouts

Obtain the remaining user lists and intended goals. Freeze source facts and case definitions
before running. Yuna/Meren have already guided discussion and been evaluated; treat them as
regressions, not unseen deck holdouts. Saheeli has also guided a worked strategy example. Select genuinely unused strategies/candidates for holdout
checks. For the later interaction trial, prepare commander-only, partial-brew direction-change,
and full-list/pending-plan scenarios. Record actual goals rather than infer them from names.

Keep additional unseen candidate cases and known rules regressions. To measure recent-pool recall,
human-review one declared eligible release pool in full; if only a subset is reviewed, report
subset recall and leave full-pool recall unknown. Do not force five suggestions when fewer are good.
Expected card lists guide recall checks, not model input, and alternatives can be judged useful.

### Comparisons

Use identical source snapshots, user constraints, and one fixed model/settings choice:

- **Local baseline:** community-free candidate discovery and transparent deterministic ordering.
- **Hybrid:** proposed names plus typed searches and model prioritization/explanation.
- **Ablation:** remove proposed-name candidates while retaining the hybrid's captured search plan
  and ranker, to measure the discovery channel's contribution.

Twelve scenarios across three arms means up to 36 advice runs, **not 36 provider calls**. Tool-using
runs may make multiple calls. Freeze actual provider-call, token, timeout, and spend caps before
asking for authorization. Check current provider pricing and reserve worst-case spend; no automatic
retries, replacement runs, or unrecorded failures. Include failed attempts in cost/completion metrics.
If needed, first compare a same-model direct decklist prompt with the current assistant as a small
control to distinguish model capability from tool/search restrictions; authorize that separately
rather than silently expanding the matrix.

Blind the user to the arm when assessing usefulness and explanations. Human judgment is primary;
a second model agreeing is not proof. Capture candidate-channel recall before ranking, final utility,
material rules errors, ambiguity, coverage, tokens, tool calls, timings, and failed attempts. Keep
all attempted cases in the report. Do not recycle failed holdouts as unseen tests after tuning.

### Proposed go/no-go gates — user approval required

| Dimension | Proposed gate |
| --- | --- |
| Utility | At least 4/5 useful suggestions on 10/12 general-brewing scenarios; hybrid wins at least 60% of blinded local-baseline comparisons. Recent-pool tasks permit correct empty results. |
| Mechanical safety | Zero observed illegal/off-color/identity/copy-limit violations, unauthorized actions, or stale mutations in the test set. |
| Rules quality | Zero observed material rules errors in at least 60 reviewed positive recommendations; report unclear claims separately. This does not prove zero future errors. |
| Discovery | At least 80% recall of independently labeled useful candidates at a frozen candidate cap; report each deck, held-out decks, and reviewed recent pool separately. |
| Coverage honesty | Exact assessed/unassessed/failed counts; incomplete discovery/assessment never presented as completed no-match evidence. |
| Responsiveness | Target local actions p95 <=200 ms, first local board <=1 second, first AI package p95 <=20 seconds on representative hardware. Small trials report raw timings, median, and maximum; later repeated measurements are needed to substantiate p95. |
| Cost | Proposed target <=$0.10 per completed advice refresh including allocated failed-attempt spend. A provisional total ceiling of $5 is not authorization and must be reconciled with priced worst-case call/token reservations. |

These are draft product targets, not measured achievements. A small trial can falsify the design;
it cannot establish universal recommendation quality or production reliability. If the hybrid does
not add useful decisions, keep local search and reconsider the model/context/discovery bottleneck
rather than expand the architecture. If quality passes but latency fails, narrow the AI interaction
frequency or scope before rollout, and rerun affected acceptance checks.

## Do not build yet

- A universal ranker or one prompt forced onto all three workflows.
- More commander-specific branches or per-error prompt warnings.
- Embeddings, a mechanics graph, formal rules engine, or new agent/job framework.
- Automatic deck edits, unbounded background assessment, or a model call per click.
- A stronger model/reasoning setting assumed to solve correctness without comparison.
- A cache that presents old-context advice as current.
- A recommendation redesign sold as a fix for unreproduced lag.

## Approval boundary

The user accepts the early suggestions and planning direction but rejects a fixed per-card
interaction schema. The eight-call Meren/Saheeli runtime-query/fact-assessment regression test is
complete, with useful findings and real gaps. Before UI work, refine source-language/query feedback
and planning-time rule access, then agree on a new bounded test including pip/devotion,
cascade-versus-cost, a genuinely unused strategy, and a fully declared release pool. Compare
admission before ranking, recommendation usefulness, interpretation errors and coverage separately.
The recovery/paired authorizations and additional two-call Sol assessment authorization are
consumed. The original Sol ledger remains stopped on unknown billing after three of four allowed
attempts. Do not make further calls or reset/resume any receipt without fresh permission.
Yuna/Meren/Saheeli are discussed regression cases, not untouched holdouts. The full architecture,
production model changes and broad implementation remain unapproved. Empty-feed/lag work is separate.

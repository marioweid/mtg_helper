# Fresh Luna refined-pipeline regression experiment

## Authorization and boundary

The user chose Luna as the inexpensive refinement baseline, keeping all work separate from the
application. They explicitly approved **at most six fresh requests**, **$0.25 estimated cap**,
**300 seconds/request**, **no retries**, with an immediate stop on unknown billing. No prior live
ledger is reset or resumed. No other model or production change is approved by this run.

Standard-tier pricing rechecked on the official Luna model page before execution: input $0.20/M,
cache writes 1.25× input = $0.25/M, output $1.20/M. All input is reserved/estimated at the upper
$0.25/M rate; no cached-token discount is assumed. UTF-8 bytes reserve as input tokens, including
prompt/schema/payload and 2,000 framing bytes. Exact six-call reservation: **$0.1355**.
This is an estimated client-side ceiling, not a provider-enforced account billing limit.

## Fixed sequence

1. Initial Meren and Saheeli plans, complete source commander facts/goals, observed Oracle prefixes,
   full rules source metadata and executable literal rule/card query instructions.
2. Execute local searches, preserving actual totals, errors, complete card samples and up to eight
   full rule entries per query. Initial planning sees no curated nine-rule diagnostic pack.
3. One revision per commander, receiving its own initial plan and actual observations. A revision
   is a **complete replacement**: dropped queries/nominations do not retain admission credit.
4. Execute replacement searches. Archive initial/replacement admission separately, then assess.
5. One assessment per commander over **the unchanged original 64 identities and candidate facts**,
   plus the revised plan, the original assessment-only rules pack and all rule entries returned
   by this commander's initial/revised searches. New discoveries are recorded, not injected into
   this review pool. Never silently truncate source facts to fit request bounds.

Order: plan Meren, plan Saheeli, revise Meren, revise Saheeli, review Meren, review Saheeli.
Input-byte/output-token bounds: plan 20,000/5,000; revise 60,000/5,000; review 95,000/10,000.
All requests use standard tier, low reasoning/verbosity, `store=False`, no hosted tools and no SDK
retries. A failed/incomplete/invalid prerequisite stops the experiment; no replacement response
is invented. Individual bad quotes remain per-candidate failures rather than poisoning valid rows.

## Measurement and fairness

Meren/Saheeli are discussed **regressions, not holdouts**. No commander-specific synergy hint,
reference decklist, diagnostic expectation, prior ranking or another model's output goes into
planning. The original nine rules still appear at assessment, not earlier. Full literal rules
lookup is not guaranteed indirect discovery; short-result ordering is not strategic relevance.

Compare initial/replacement searches and nomination/shortlist admission, explicit misses/errors,
quotation/identity/coverage conformance, inspected rules explanations, latency and estimated cost
separately. Diagnostic match/admission is not precision or win rate. Correct quotations do not
prove interpretation. Six calls versus the old four Luna calls means cost/latency is not a pure
model-speed comparison. Prompts, output schema and planning context change together; any result
supports the composite pipeline, not attribution to one individual improvement.

The shared API wrapper adds only an explicit optional stage argument; old callers/prompts/default
profiles remain unchanged. The new single-use ledger is owned by a separate runner, not the app.

## Reproducibility

From `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_luna_refined_check
uv run --no-sync python -m scripts.commander_discovery_luna_refined_check --summarize
```

Preparation needs pinned existing source caches and original baseline receipts; it freezes
`inputs.json`. Execution checkpoints `results.json` before each HTTP attempt and freezes exact
payload/prompt/schema files under `requests/` and provenance under `observations/`. A second live
invocation refuses the ledger even after a failure. **Never delete `results.json` to rerun.**

Offline checks and independent money-boundary review precede the single authorized live run.

# Result-aware search refinement — controlled Yuna/Meren evaluation

## Outcome

**Stopped after two baseline calls, before either refinement.** Meren returned 13 Oracle tags
against an eight-tag limit, including one UUID outside the supplied menu and absent from the local
source. Backend validation correctly rejected it; no trimming or retries were used. Estimated
token cost was **$0.009647**. The refinement hypothesis remains untested, not disproven.

See [the lead report](report.md) for the source-grounded Yuna review, exact recovery, preserved
failure and recommendation to fix model-output reliability before another refinement experiment.

## Pre-call protocol (October 30, 2026)

The user asked the assistant to lead this evaluation and explicitly approved four fresh calls
under a **$0.15 total estimated-cost ceiling**. Previous experiment authorizations remain spent.
No retries, paid per-card grading, application changes, saved-deck edits, or deployment.

Use the current production setup as baseline, then one complete replacement refinement per deck.
Only refinement receives actual query counts and deterministic samples of public source facts.
Keep eligibility, source menu, commander facts, strategy, term budget and popularity ranking fixed.
No reference identities, evaluator labels, earlier model outputs or earlier experiment card
suggestions enter generation. Freeze all source/ranking/code/fixture bindings and exact requests.

Call order: Yuna baseline → Meren baseline → Meren refinement → Yuna refinement. Freeze each
refinement request before attempting it. An exclusively created ledger refuses all repeats and
resumes, even after interruption. A failed/unknown/incomplete or invalid call stops dependent work.

Per-search sample positions, before deduplication: first, second, middle, penultimate, last.
At most five samples, no filler. Include combined top-ten facts, zero counts and broad counts.
Selection uses production ordering only, never target overlap or parent-selected "good" cards.
The revision can keep a useful search, narrow it, replace it or remove it within the same schema;
there is no mandated role quota, count threshold, card exception list, or new scoring weight.

Pricing checked against the official `gpt-5.6-luna` model page on October 30: input $0.20/M;
cache-write upper estimate $0.25/M; output $1.20/M. Two 80K/4K baseline bounds plus two 120K/4K
refinement bounds reserve **$0.1192**, below $0.15. Request bounds count UTF-8 bytes plus framing
conservatively as input tokens; facts are never silently truncated to fit. Actual receipts remain
separate from estimates. Unknown costs are not zero. No model change or tool calls.

## Review and decision rules

After all four calls, prepare one packet per deck: commander, historical strategy brief, and
the deduplicated union of top-20 cards, alphabetically sorted, with full source facts. Hide arm,
rank and reference membership during grading. This reduces presentation bias but cannot make the
assistant forget previous discussions; it is not an independent blinded human evaluation.

Assign one consistent card/deck rating, with literal Oracle quotation and a concrete reason:

| Rating | Score | Meaning |
| --- | ---: | --- |
| direct | 2 | Concrete connection to the declared engine or an explicitly requested function |
| support | 1 | Useful general infrastructure, without a special engine claim |
| conditional | 0 | Needs a meaningful unstated package/resource, or claimed trigger compatibility is absent |
| uncertain | 0 | Missing source/rules/context prevents a reliable strategic judgment |
| off_plan | -1 | No reasonable supplied-plan connection, or an unestablished liability dominates |

Same card in both arms receives the same rating. Generic staples are not automatically bad;
off-list alternatives receive no penalty for being absent from the reference deck. Do not invent
a bracket, budget, infinite-combo ban or pace constraint. Distinguish cast/entry/death timing,
front/back access, permanent/player counters, beneficial/detrimental triggers and target restrictions.

Primary adoption gate: weighted top-20 fit improves on **both** decks; off-plan counts do not
increase; each refined pool retains at least 90% of baseline-reachable reference identities.
Report every component, including failed gates. Supplement with reference hits at 10/20/50 and
full-pool recovery, query/sample counts, latency and token cost. No precision/accuracy claim from
exact recovery. These are two known regression decks and one model sample per stage/deck.

## Artifacts / execution

`inputs.json` freezes protocol and baseline requests. `requests/` freezes actual per-attempt
requests (including revision observations). `attempts.json` is the one-shot ledger. `results.json`
contains local ranked outputs and recovery. `review-packet.json` hides arm/rank/reference identity
flags for the lead review. `ratings.json` and the final report follow only after calls complete.

All execution and verification use explicit local `docker-compose.yml`. Preparation/replay/tests
use `OPENAI_API_KEY=test`; only the single authorized `--live` run uses the existing secret without
printing it. Read-only source transactions and data fingerprints reject changed comparison data.

From the repository root, preparation only (no model requests):

```powershell
docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --volume "${PWD}/docs/research/discover-result-aware:/workspace/docs/research/discover-result-aware" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --frozen python -m scripts.result_aware_calls
```

The single authorized run uses the same command with `--live`, removing `-e OPENAI_API_KEY=test`.
Once `attempts.json` exists, do not remove it or attempt another paid run. Use `--summarize` with
the dummy key for local replay; `--grade` validates and applies the lead's completed ratings only.
Scoring uses the immutable public card snapshot and saved rankings, not a newly downloaded source
or current rank metadata. Reference fixtures must still match their frozen hashes.

Offline gate:

```powershell
docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --extra dev --frozen pytest -q -W error -m no_db tests/test_result_aware_eval.py tests/test_result_aware_calls.py -o cache_dir=/tmp/pytest-cache
```

The sampling behavior was observed red before implementation. Thirteen offline checks passed before calls,
including complete literal-quote grading, hidden arm/reference metadata, two-deck adoption gates,
scope/reservation/output bounds, frozen checkpoints, own-baseline-only refinement, no-repeat,
changed-source, invalid-output and unknown-usage stops. A subsequent frozen-failure regression brings
the final scoped count to fourteen. Scoped Ruff lint/format and ty checks pass.

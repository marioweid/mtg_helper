# Commander planning and discovery — pre-run protocol

## Now

The user authorized **Full paired test — $1 cap**: up to eight application model requests,
no retries, no production changes. **All eight calls are now complete, with no retries, for
$0.33604205 conservative estimated API cost. Authorization is exhausted.** The setup below was
frozen before execution; see README.md for measured results and limitations.
The earlier four-call recovery authorization remains exhausted and untouched.

## Question

Can Luna/Terra generate useful commander-specific plans and executable searches, including
indirect interactions, then assess supplied candidate facts accurately? This is a regression
smoke test on already-discussed Meren and Saheeli, not an unseen-strategy benchmark or proof
of complete catalog/new-release discovery. The parent-written examples are not model results.

## Frozen setup

- Original hash-verified Scryfall Oracle archive, updated `2026-10-04T21:01:57.080+00:00`.
- Dates from the earlier derived first-paper catalog, with its file hash frozen. Recent sampling
  means first observed paper date after the models' documented `2026-02-16` cutoff and no later
  than the source snapshot's `2026-10-04` date. This cannot prove absence from model training.
- Two commander-only goals in `backend/evals/commander_discovery/cases.json`. No actual decks,
  user reference lists, budget/bracket/combo restrictions, community data or embeddings.
- Planning gets only commander source facts, the goal, generic planning instructions, and the
  documented source-search contract. No worked examples, diagnostic names/checks, or rule pack.
- Identical planner prompts/payloads/settings for both models. Up to eight searches and twelve
  named candidates. Low reasoning/verbosity; 5,000 output tokens per plan.
- Review gets complete source facts for the identical common pool per commander, plus nine
  excerpts of the official `2026-09-25` Comprehensive Rules. No planner responses, provenance,
  expectations, or diagnostic labels. Rules explicitly include proliferate: assessment of that
  interaction is therefore grounded/aided, not evidence of unprompted planning discovery.
- Review every candidate exactly once, then rank up to fifteen with no filler quota. Low
  reasoning/verbosity; 10,000 output tokens per review. Judgments concern proposed inclusions,
  not an existing physical deck. Inter-candidate packages must stay conditional.
- No tools, `store=False`, SDK retries zero, timeout 120 seconds. One observation per stage,
  commander and model; no prompt tuning or additional requests within this authorization.

## Retrieval and attribution

Execute a small typed source interface locally, without a database:

- Case-insensitive literal all/any Oracle substrings.
- Any printed type-line substring; exact source keyword membership (unrestricted strings).
- Mana-cost substring presence, **not pip counts**.
- Inclusive source card-level mana-value bounds.
- Populated fields AND together; alternatives within an `any` field OR together.

Search text/types/costs span all faces for recall, without asserting simultaneous face access.
Every channel enforces paper shape, source Commander legality, commander exclusion, color identity,
and nonland status. Whole names resolve before unique front aliases. Spell-front MDFCs are allowed.
Empty, nonfinite, blank/oversized-term, and inverted-range queries fail explicitly per query.
Unsupported schema fields are never silently interpreted as a different operation.

Each query records total matches and truncation and samples up to eight identities using a stable
hash of the source/case/query. Interleave query samples up to twenty; interleave these with up to
twelve eligible nominations for an independent shortlist of at most 32 per model. No popularity
ordering. Quoted matching terms are clues, never proof of a mechanical role or fit.

The common review pool contains:

1. The fixed diagnostic cards (13 Meren, 16 Saheeli), including useful, limited and counterproductive
   cases from the worked discussion. This deliberately biases the pool toward regression checks.
2. Up to eight seeded recent eligible designs absent from either independent shortlist/diagnostics.
3. Interleaved independent model shortlists until a maximum of 64 distinct identities is reached.

Review order is independently hash-shuffled and identical between models. Record nominations,
query matches, independent shortlist membership, forced diagnostics, recent-scout additions and
actual review membership separately. A diagnostic can also have been independently discovered,
but mere inclusion in the common review pool is **never** credited as planning/search success.
Broad matching totals are not admitted-candidate recall. Recent sampling is not release coverage.

## Paid boundary and reservation

Fixed order:

1. Meren/Terra plan
2. Meren/Luna plan
3. Saheeli/Luna plan
4. Saheeli/Terra plan
5. Meren/Luna review
6. Meren/Terra review
7. Saheeli/Terra review
8. Saheeli/Luna review

Conservative pricing was checked against the official model pages before preparation:

| Model | Input / million (cache-write upper rate) | Output / million |
| --- | ---: | ---: |
| `gpt-5.6-luna` | $0.25 | $1.20 |
| `gpt-5.6-terra` | $2.50 | $12.00 |

Reserve input using UTF-8 bytes of prompt + schema + payload, plus 2,000 framing tokens. Total
bounds are 20,000 per planner and 70,000 per reviewer, far below long-context price thresholds.
Combined with output caps, the eight-call reservation is **$0.891**, within the $1 authorization.
This is a conservative token-cost estimate, not an invoice guarantee; coding/review sessions are
outside the application budget. Unknown billing remains explicitly unknown, not a zero charge.

`inputs.json` freezes source/fixture/derived-catalog hashes, prompts, schemas, settings and prices.
Before review calls, freeze exact common payloads in `assessment-inputs.json` and provenance in
`retrieval.json`. Never trim source text to fit: an oversized request stops without sending it.
`results.json` is exclusively created; checkpoint every attempted request before contacting the
provider. Repeat, concurrent execution and resume are refused. Provider errors, missing/invalid
usage, unexpected response models or usage beyond reservation stop subsequent requests. Priced
incomplete/malformed outputs remain failures; no retries. Independent guard review precedes live.

## Evaluation and interpretation

- Read the actual plans, their proposed indirect links, executable query results and nominations.
- Record diagnostic admission at matching, sampling, independent shortlist and review stages.
- Mechanically validate review membership, uniqueness, completion and exact quote grounding.
  Invalid quotes do not erase independently grounded items; missing/duplicate/unknown keys remain
  reported. Weak/uncertain cards must not be included in the ranked recommendations.
- Manually inspect diagnostic mechanisms and final recommendations against supplied facts/rules.
  Quotes and structured output do not certify semantics. Do not publish a semantic-accuracy score
  without a defined reviewed denominator, or mistake model fit labels for validated correctness.
- Distinguish retrieval misses from judgment mistakes. Compare judgments fairly on the shared pool;
  track whether each recommended card came from that model's own discovery or another channel.
- Capture actual requests, tokens, cost estimates and per-stage timing. No latency percentiles or
  production promises follow from eight calls.
- Give the user the real plans and ranked cards, with limitations and supported rules errors.
  There is no invented numerical pass threshold; user usefulness and critical interaction checks
  determine whether a larger, untouched-strategy test is warranted.

This does not test a visual UI, complete release traversal, full-corpus recall, goal-change caching,
combo certification, deployed empty-feed behavior, or application lag.

## Commands

From `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_check
uv run --no-sync pytest -q -W error tests/test_commander_discovery_check.py tests/test_commander_discovery_run.py
uv run --no-sync python -m scripts.commander_discovery_check --summarize
```

`--live` is authorized once for this frozen protocol. **Do not delete results to rerun it.**

# Sol extension — frozen comparison protocol

## Now

Run stopped after three attempts: two completed plans, then Meren assessment timed out at the
120-second client limit. Usage/billing is unknown; no retry and no Saheeli assessment request.
See [README.md](README.md). The prospective protocol below was frozen before paid execution.

## Authorization

The user explicitly authorized **four new application API calls**, no retries, **$1 conservative
estimated ceiling**, no production changes. This authorization is separate from the exhausted
Luna/Terra planning test and recovery test. Do not rerun those models or delete prior results.

Calls, once each and in order:

1. Meren planning — `gpt-6.1-sol`
2. Saheeli planning — `gpt-6.1-sol`
3. Meren assessment — `gpt-6.1-sol`
4. Saheeli assessment — `gpt-6.1-sol`

## Comparability

- Same hash-verified October 4 Scryfall snapshot, commander facts, goal briefs, planning prompt,
  review prompt, schemas, output caps, low reasoning, low verbosity and nine official rules excerpts.
- The exact two prior 64-card assessment payloads are copied byte-for-byte. Their request hashes
  must match both completed prior reviews; planning payload hashes must match prior plans too.
- No fixes to earlier quote/identifier weaknesses, no extra proliferation hints and no model feedback
  loop. Preserve the baseline shortcomings rather than giving Sol a different test.
- Execute Sol's generated searches locally using the same source eligibility, seed and budgets.
  Record its independent admission separately. Do **not** add its discoveries to the fixed review
  pools or credit existing diagnostics/other models' discoveries to Sol.
- No reference deck lists, diagnostic expectations, provenance labels, prior model outputs or
  parent-generated worked examples are supplied to planning or assessment.
- These are discussed regression cases, not untouched holdouts. No full release enumeration or
  full-catalog coverage claim is possible. This does not reproduce the application feed/lag issue.
- Sol's documented cutoff is April 30, 2026, versus February 16 for the prior models. The pool remains
  fixed for judgment comparison; release after the old cutoff is not necessarily novelty for Sol.

## Spending and execution

Official [Sol model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol.md)
checked before execution: $2/M uncached input, $2.5/M cache writes, $0.1/M cached input, $10/M output.
Use $2.5/M for **all** input as a conservative upper rate; do not assume caching discounts.

Each plan is bounded at 20,000 input bytes (reserved as tokens) and 5,000 total output tokens.
Each review is bounded at 70,000 input bytes and 10,000 total output tokens, including reasoning.
Prompt/schema/framing are included. Total reserved estimate: **$0.75**, below the authorized $1 cap.
No tools, retries, Fast mode, batching or production model changes are requested.
Before any Sol request, the preparation receipt was amended to explicitly pin
`service_tier=default`; missing/nondefault returned tiers stop as unknown pricing. SDK documentation
confirmed that omission inherits project configuration. Prompts, schemas and request-payload hashes
were unchanged. Prior response tiers were not recorded, so timing comparisons retain that caveat.

`backend/scripts/commander_discovery_sol_check.py` reuses the tested single-use attempt ledger,
SDK retry refusal, pre-send byte bounds, remaining-spend reservation and unknown-billing stop.
It checks frozen assessment bytes before execution and again before building reviews. Every attempt
is checkpointed before its HTTP request. Provider/usage failures stop rather than retry; quality
failures remain evidence. An existing `results.json` blocks another live execution or paid resume.
The four-call profile is fixed in code, not selectable through arbitrary model/budget flags.

## Evaluation and reporting

Compare plan intentions, query totals/zero results, independent shortlisted diagnostic admission,
source-only discoveries and supported strategic interpretations. Assess the identical candidate
pool for quote/ID conformance and manually inspect nuanced mechanics. Grounding validation is not
semantic accuracy. Report latency, conservative estimated cost and incomplete/failed states.
Archive raw outputs plus readable rankings; do not repair the frozen scorer to improve results.

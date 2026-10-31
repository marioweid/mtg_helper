# Lead assessment: result-aware refinement

## Decision

**Do not adopt result-aware refinement yet: the controlled comparison did not reach refinement.**
The current setup first needs a more reliable model-facing output contract. Meren's baseline
exceeded the existing eight-tag budget and included an identity absent from both its supplied
catalog and the local source. Production validation correctly rejected it. The predeclared stop
rule prevented both refinement calls; no retry, trimming, replacement or hidden repair occurred.

This does **not** establish that refinement is ineffective. There is no completed baseline/refined
pair for either deck, so its quality, coverage, latency and incremental cost cannot be assessed.

## Execution

| Stage | Provider outcome | Application-contract outcome | Conservative token estimate |
| --- | --- | --- | ---: |
| Yuna baseline | Completed, 9.30 seconds | Valid; ranked locally | $0.004573 |
| Meren baseline | Completed, 11.74 seconds | Rejected; not ranked | $0.005074 |
| Meren refinement | Not attempted | Stopped by protocol | — |
| Yuna refinement | Not attempted | Stopped by protocol | — |

Two of four planned calls were attempted. **33,179 input / 1,126 output tokens**, known estimated
cost **$0.009647**, no unknown-cost attempt. Reservation was $0.1192 under the approved $0.15 ceiling.
No paid per-card reviews, application/deck edits, migrations, deploys or further provider requests.
The remaining requests were unused, not silently repurposed as repairs under a no-retry protocol.

## Confirmed contract failure

The exact preserved Meren output reproduces this backend error offline:

> Searches permit at most 8 distinct terms of each kind

It contains six searches and **13 distinct Oracle-tag identities**, rather than the permitted eight.
All six individual searches fit the provider-facing shape. In addition,
`524845ed-ea82-4a60-8b52-8a38ab06a503` is not in the 160-tag supplied menu and does not exist in the
local source. That identity would remain invalid even if the tag-count limit were relaxed.

The frozen provider schema permits up to **40 tags per group** and requires UUID syntax; it does
not enumerate the allowed source identities or express the cross-query eight-distinct-tag limit.
The stricter source-membership/global-budget conditions are implemented by application validators
and stated in the prompt, not enforced by that provider schema. Structured JSON completion is
therefore not synonymous with a valid application search plan. This is an observed contract gap,
not an estimated production failure rate from two samples.

See `failure-analysis.json`, the original request/receipt, and the frozen-failure regression test.
The application is doing the safe thing by rejecting the output rather than accepting unknown tags
or discarding arbitrary choices. No invalid Meren plan was credited as a successful baseline.

## Lead review of Yuna's valid baseline

The review packet was sorted by card name and hid arm, rank and reference flags. Ratings were written
and literal source quotations validated **before reading recovery metrics**. The evaluator is the
lead assistant, not an independent human; previous discussions cannot be forgotten. No reference-list
penalty or unstated bracket, budget, combo prohibition or pace limit was applied.

All twenty cards plausibly fill either counter-engine functions or the brief's explicitly requested
creature-based acceleration. The predeclared rubric therefore assigns twenty `direct` grades,
**40/40 weighted points**, with no clearly off-plan card. This is not 100% recommendation accuracy,
an optimization claim, or proof that these are the best twenty cards to show together.

Strong concrete examples:

- **Kami of Whispered Hopes:** power-based mana directly benefits from counter growth; its counter
  replacement applies to permanent +1/+1 counters, not proliferating player counters.
- **Forgotten Ancient / The Ozolith:** explicit counter accumulation/redistribution or preservation.
- **The Great Henge:** mana, nontoken creature-entry draw and counters; the discount needs creature
  power, and tokens do not trigger its nontoken draw ability.
- **Walking Ballista:** a counter-consuming damage outlet, without claiming an infinite combo.

Important qualifications are retained in `ratings.json`: simple mana creatures do not gain greater
mana output merely from +1/+1 counters; Faeburrow Elder's own stat bonuses are not counters; Selvala's
draw is conditional and can benefit opponents; Delighted Halfling's colored mana is legendary-only.

**Composition remains a separate concern.** Fourteen of the twenty are mana-producing/assisting
creatures, counting Treasure generation and granted mana abilities; The Great Henge also produces
mana. Many individually sensible ramp alternatives can crowd out other engine options on a first
page. This is worth evaluating, but is not a reason to relabel those cards as unrelated or invent
fixed deck-role quotas. The current rubric saturates when explicit creature-ramp fulfillment and
distinctive counter-engine connections share the same grade. A future comparison should distinguish
those contributions before running, not change grades afterward to force a positive result.

Recovery, inspected after grading:

| Valid Yuna baseline | Result |
| --- | ---: |
| Reference hits in first 10 | 2 |
| Reference hits in first 20 | 4 |
| Reference hits in first 50 | 10 |
| Reachable reference identities | 34/65 |
| Eligible matching pool | 1,826 |

The disparity between 4/20 exact recovery and a reasonable individual-card review illustrates why
off-list is not automatically wrong. No equivalent Meren quality score or refined score exists.
The adoption gates fail closed as **missing complete pairs**, not as measured quality regressions.

## Recommended next step

1. **Fix output reliability first.** Consider a model-facing global choice list capped at eight
   tags/eight keywords, with catalog-enumerated identities and query references into those choices.
   Decode it into the existing saved-search representation. Keep server-side validation. This could
   make the observed impossible-to-accept outputs structurally unavailable without manual trimming.
   It is a proposal, not an implemented or tested fix from this run.
2. Add a fresh comparison rubric separating distinctive engine connections from otherwise useful
   requested ramp, so it can detect first-page redundancy without mandatory role balancing.
3. Only then rerun a newly authorized, frozen baseline/refinement comparison on both regression
   decks. Keep model, source, ranking and term budgets fixed. Do not infer unseen-deck performance.

No production behavior changed. The already-shipped setup still preserves saved strategies on
validation errors; this experiment does not authorize automatic retries or an extra setup call.

## Verification and artifacts

- Thirteen offline checks passed before spending. After the observed failure, a frozen-output
  regression was added: **14 scoped checks pass**, with Ruff lint/format and ty clean.
- Production SQL sampling and immutable-snapshot decoding were dry-run read-only before calls.
- The sampling test was observed red before implementation; source/quote/coverage and one-shot
  guards are exercised with only external database/provider IO substituted.
- `inputs.json`: source/ranking/code/fixture hashes, current-production baselines, bounds and order.
- `requests/yuna-baseline.json`, `requests/meren-baseline.json`: exact checkpointed requests. There
  are no refinement request files. `attempts.json`: both original receipts/outputs and stop marker.
- `results.json`: frozen ranking/recovery and explicit Meren error; `review-packet.json`: stripped
  review inputs; `ratings.json`: all twenty sourced rationales and an empty, unscored Meren set;
  `graded-results.json`: failed-closed complete-pair gates; `failure-analysis.json`: contract gap.
- All source access used read-only transactions on explicit isolated Compose PostgreSQL. Original
  earlier experiments and their spent authorizations were preserved.

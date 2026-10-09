# Sol comparison — original partial run, stopped without automatic retry

## Follow-up

The user subsequently authorized a **separate two-call assessment run** with a 300-second timeout
and $0.60 additional cap. Both completed. See the [completed comparison](../commander-discovery-sol-assessment/README.md).
This original three-attempt receipt is unchanged; its timeout remains potentially billed and
whole-Sol total cost is still unknown. The historical state below describes this first run.

## Original stopped state

The user authorized four new Sol application requests, no retries, $1 conservative estimated cap.
**Three requests were attempted.** Both plans completed; Meren assessment hit the 120-second
client timeout. Usage/billing for that attempt was not returned. The guard stopped and **Saheeli
assessment was not sent**. No retries, additional calls or production changes occurred.

Known conservative estimated cost for the two completed plans: **$0.03234**.
**Total actual/estimated cost is unknown**, not $0.03234: one potentially billed attempt is unpriced.
The pre-run upper reservation was $0.75. Preserve the failed receipt; do not delete it or resume
this single-use live ledger. One originally authorized request remained unissued when the guard
stopped. Completing assessment requires discussing a fresh bounded authorization, not silently
using that unused slot or relaxing the unknown-billing stop.

- [Protocol](protocol.md)
- [Actual plans and local shortlists](plans.md)
- `inputs.json`, `assessment-inputs.json`: frozen setup and unchanged two 64-card baseline pools
- `results.json`: all attempts, including the sanitized timeout failure
- `retrieval.json`: independently executed Sol queries and admission, not fabricated assessment
- `summary.json`: explicit stopped state, three attempts and one unpriced attempt

## Observed results

| Request | Result | Observed latency | Conservative estimated cost |
| --- | --- | ---: | ---: |
| Meren planning | completed | 33.1 s | $0.0158375 |
| Saheeli planning | completed | 37.5 s | $0.0165025 |
| Meren 64-card assessment | APITimeoutError | 120.0 s client limit | unknown |
| Saheeli 64-card assessment | not sent | — | — |

The timeout is a transport observation, not evidence of an invalid response, bad Magic reasoning
or an incomplete provider generation. The provider might still have processed/billed the request.
There is no returned assessment text to evaluate. Do not compare Sol's quote grounding, ranking
quality, Sundial explanation or rules accuracy against the completed prior assessments.

## Useful planning evidence

- Sol independently nominated **Sundial of the Infinite** and **Brudiclad** for Saheeli, and generated
  a separate retention/value search for `end the turn`, `populate` and sacrifice outlets. Sundial
  was previously only a forced diagnostic. This is a real planning/discovery improvement on the
  temporary-copy connection, **not** proof Sol correctly executes its tricky timing or copy rules.
- Its Saheeli artifact-entry query used `enters` and matched **720** cards, rather than Terra's
  obsolete literal phrase that returned zero. Sol's Meren entry-interaction query matched 144.
  No Sol query returned zero; broad matching still does not prove quality or coverage.
- Its Meren outlet search allowed both `Sacrifice a creature` and `Sacrifice another creature`,
  without requiring an explicit timing clause. It matched 340 cards and included Viscera Seer and
  Yawgmoth in the matching universe. **Yawgmoth was not actually shortlisted.** Query-match coverage
  is different from admission to the small model-review pool.
- All 12 initial nominations per case resolved and passed eligibility. Meren nominations include
  cheap outlets, reusable utility bodies, Skullclamp, Pitiless Plunderer and Living Death.
- Sol **still did not mention/search for proliferate** in Meren planning. Cankerbloom and Evolution
  Sage were not independently shortlisted. This shared omission remains uncorrected.
- Its deliberately broad Saheeli attack search used `whenever`/`combat damage`, so many matches
  need actual judgment. Some relevance problems remain; better query syntax is not full discovery.

### Independent diagnostic admission (not strategic precision)

| Model | Meren shortlist | Saheeli shortlist |
| --- | ---: | ---: |
| Luna | 4/13 | 1/16 |
| Terra | 3/13 | 7/16 |
| Sol | 4/13 | 6/16 |

These fixture sets include negative/conditional cases and are not all "desired cards". This is not
reference-deck recovery, recommendation accuracy or a model-win score. Sol's six Saheeli diagnostic
admissions were Brudiclad, Decoction Module, Panharmonicon, Sundial, Whirler and Wurmcoil. Each model's
own independently admitted cards are distinguished from forced diagnostics and shared-pool cards.
No new Sol discoveries were inserted into the fixed assessment requests.

## Interpretation and limitations

Sol's planning is encouraging on Saheeli retention and source wording, but the Meren indirect
counter connection remains missing. Both Sol plans were slower than the observed Luna plans;
judgment latency and cost cannot be compared because assessment did not complete at the client.
The identical 120-second timeout was insufficient for this Sol assessment workload. A further
assessment test would need a longer transport window, explicit fresh call authorization and the
same prompts/caps/pools. Do not infer that increasing the timeout alone guarantees success.

These are discussed regression examples, not untouched holdouts or full release sweeps. Sol's
April 30, 2026 cutoff is later than the previous models' February 16 cutoff; some originally
post-cutoff cards are therefore not necessarily novel to Sol. Model training absence is not proven
by release dates. Sol explicitly requested standard tier; prior response tiers were not recorded.
No production model switch, completed architecture proof or deployed feed/lag fix follows.

## Verification

Before live execution: **97 offline tests** passed with warnings as errors, scoped Ruff lint/format
and `ty` passed, and function/parameter bounds passed. An independent read-only budget/fairness
review plus one focused standard-tier recheck found no supported blockers. Those were spending
reviews, not certification of generated Magic advice. Old Luna/Terra JSON remained byte-identical.

The budget arithmetic and explicit-tier test were observed red before their implementation/fix.
Standard processing is pinned and missing/nonstandard returned tiers are treated as unpriced.
All three attempts were checkpointed before HTTP; the failure has no automatic retry.

Offline replay from `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_sol_check --summarize
```

**Do not rerun `--live`, delete `results.json`, or claim the timed-out call was free.**

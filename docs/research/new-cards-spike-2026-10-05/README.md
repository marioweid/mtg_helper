# New Cards feasibility checks — 2026-10-05

**Latest follow-up:** the separately authorized eight-call
[low/high reasoning comparison](quality-v3-report.md) completed on 2026-10-06. High reasoning caught
an important combo constraint but did not eliminate rules errors and was much slower. The earlier
[v2 experiment](quality-v2-report.md) repaired identity binding, not explanation reliability.
The report below describes the preserved **v1 baseline**, not either follow-up.

## Decision

**Data acquisition is practical, but eligibility/expiry normalization needs work. The first
recommendation baseline is not safe to ship unchanged.** Cost is small; correctness and output
reliability are the blockers. No production database, deck, application service, or deployed setting
was changed. Eight OpenAI experiment calls were made; there were no automatic retries.

The user resolved an expiry question discovered in this run: use the **main Commander-playable
release**, not an early promotional printing, to start the 60-day window. First normal release is
not automatically proof of Commander legality; verified product rules still matter.

## 1. Full-export data check

Run on 2026-10-05 against Scryfall's 2026-10-04 exports. See `data-report.json` for source timestamps,
byte sizes, SHA-256 hashes, counts, and examples. This streamed both archives locally and called the
existing importer's actual mapping/eligibility functions, without connecting to a database.

| Measurement | Observed |
| --- | ---: |
| Default Cards printing records | 118,475 |
| Structurally plausible paper printings | 98,755 |
| Oracle representative records | 38,705 |
| Recent paper identities under earliest-paper-date rule | 495 |
| Upcoming under earliest-paper-date rule | 168 |
| Upcoming retained by existing importer | **0 / 168** |
| Recent retained by existing importer | 492 / 495 |
| Old identities falsely new using representative date | **204** |
| Recent identities losing their rules text in current mapping | **38** |
| Upcoming identities without preview metadata | **167 / 168** |
| Recent identities without preview metadata | 348 / 495 |
| Combined compressed download | 103,292,564 bytes (~98.5 MiB) |
| Download time, both archives | 3.35 seconds |
| Local scan/reduction/mapping time | 5.38 seconds |

Timing is one workstation observation, not a production VM benchmark; database-write time, peak
memory, scheduler behavior, and total application sync cost were not measured.

### What this proves

- A daily shared bulk pass is plausible. No per-deck Scryfall scrape is needed.
- Existing import rules discard previews. All 168 future-first-print candidates were `not_legal`.
- Preview metadata is too sparse to be an ingestion requirement.
- Representative printing dates are not usable as first-release dates. Example: Command Tower's
  representative is dated 2026-10-02, but its earliest paper printing is 2011-06-17.
- Both-face ingestion is required. The 38 count detects complete loss of face-only text; it is not
  a comprehensive count of every possible multiface representation error.
- Name-only joins are unsafe even in a probe: the export contains both the playable Llanowar Elves
  and a same-named token with different Oracle IDs. A regression test now covers this collision.

### New expiry edge case: early promotional cards

The export includes these `pmei` promo dates, while their `trc` main release is 2026-11-13:

| Card | Earliest paper date | Earliest + 60 days | Main release |
| --- | --- | --- | --- |
| Spock, Logical Choice | 2026-09-04 | 2026-11-03 | 2026-11-13 |
| Picard, Steadfast Captain | 2026-09-04 | 2026-11-03 | 2026-11-13 |
| Benjamin Sisko, Besieged | 2026-09-08 | 2026-11-07 | 2026-11-13 |

All three were still Commander `not_legal`. These are the three recent-first-date records rejected
by the importer. They demonstrate that even the minimum paper date can expire a preview too early.
The data report deliberately preserves this measured, superseded date rule rather than silently
changing the counts after the user's decision.

### What remains unproven

The 663 records are structural candidates, **not 663 certified Commander recommendations**.
The structural filter is deliberately not a future-legality certification algorithm. Product
exceptions, promo-only originals, withdrawn cards, and delayed legality need explicit normalization.
There are also 83 reversible-card printing records without top-level Oracle IDs; this probe excludes
those rather than proving face-identity handling. Migrations and future release corrections were
not exercised against a live local database. No undated-paper records were observed by the reducer.

## 2. Quality and cost check

### Setup

- App model: `gpt-5.6-luna`, reasoning low, structured output, `store=False`, no tools.
- Four public, hand-authored 100-card fixtures: Alela artifacts, Alela enchantments, Camellia Food,
  and Talrand spells. Each contains 62 nonland cards, 37 basic lands, and its commander.
- Scryfall validated fixture names, current legality, and color identity. These are deliberately
  simple diagnostic decks, not optimized lists, user decks, or representative mana-base samples.
- Per deck: six historical controls plus eight seeded samples from the recent, legal,
  color-compatible pool. The two Alela decks receive the same recent sample.
- Historical controls deliberately bypass age for evaluation only; they are not proposed feed items.
- One normal-order and one reversed-order request per deck: **eight calls**, 112 expected judgments.
- Public exact Oracle rules/layout were supplied, but power/toughness/loyalty and external keyword
  rules/rulings were omitted. Do not describe the inputs as complete gameplay information.
- Only public/synthetic evaluation data was sent to the model, not private decks or account IDs.
  The configured OpenAI key was read locally without printing it.

### Measured results

| Measurement | Result |
| --- | ---: |
| Completed provider responses | 8 / 8 |
| Responses meeting ID/coverage/reference contract | **4 / 8** |
| Broad scored historical labels matching expected ranges | 44 / 46 |
| Forward/reverse pairs with IDs present in both responses | 54 / 56 |
| Changed labels among those comparable pairs | **9 / 54** |
| Input tokens | 84,158 |
| Output tokens, including reasoning | 12,848 |
| Request latency range | 12.57–15.64 seconds |
| Median request latency | 14.12 seconds |
| Conservative token-cost estimate, eight calls | **$0.0364571** |

All responses were parseable structured JSON. The 4/8 failure rate concerns additional application
contracts: extra/duplicate/mistyped candidate IDs and, in one response, non-exact support names.
The validator caught these failures; they must not be treated as successful production batches.

The initial raw run counters show 46/48 broad label matches. Two entries were all-label Ashnod's
Altar controls intended for prose inspection and provided no label discrimination. Offline summary
correctly excludes them, yielding 44/46. Raw outputs/counters are preserved without retroactive edits.
One miss was a mistyped Mirkwood Bats ID; the other was a defensible downgrade of Metallurgic
Summonings to Worth testing. **44/46 is not semantic accuracy, recommendation precision, or recall.**

One order-reversal pair cannot separate positional effects from ordinary sampling variability.
Recent candidates were sampled, not exhaustively labeled; discovery recall remains unmeasured.

### Useful signal

The model consistently treated Sai/Vedalken Archmage as strong in the artifact-heavy Alela deck,
while Mesa Enchantress was strong in the enchantment-heavy list, not the artifact list. It also
rejected the out-of-color and already-present historical controls. This is evidence that actual
list context matters, not proof of general ranking quality.

### Concrete rule/grounding failures

These were checked against the archived inputs, including a second independent agent review:

1. **Wizard's Staff, reversed artifact run:** rejected because Alela is not a Wizard. Its text
   includes unrestricted `Equip {3}`; Wizard status only affects the cheaper equip ability.
2. **Emrakul, the Exigent Doom, Food run:** treated the ward sacrifice as a burden on its controller.
   Ward instead charges the opponent targeting it. The final rejection may be reasonable, but the
   explanation is wrong.
3. **Fateful Discovery, artifact run:** said artifact entries also trigger Alela. Alela triggers on
   casting; tokens and returned artifacts can trigger Discovery without triggering Alela.
4. **Ashnod's Altar, Food run:** said it cannot trigger Camellia because it sacrifices creatures,
   not Foods. The physical list includes Food creatures, such as Tough Cookie and Gingerbrute.
   Sacrificing ordinary Squirrels does not trigger Camellia; sacrificing a Food creature does.
5. **Mirkwood Bats:** a response invented a 2/1 body despite P/T not being supplied. This illustrates
   both the input-completeness limitation and the need to avoid unsupported factual embellishments.

Correct-looking labels did not ensure correct explanations. Strong recommendations are not yet
safe to expose without better grounding and validation.

### Cost interpretation

Official Luna prices checked during this task: $0.20/M input, $0.02/M cached input, $1.20/M output;
cache writes cost 1.25 times normal input. The estimate conservatively charges **all** input at
$0.25/M, plus actual output usage. It is not an invoice and excludes this coding session/review.
Source: https://developers.openai.com/api/docs/models/gpt-5.6-luna.md

Each batch cost approximately $0.0043–$0.0049. Full color-compatible recent pools were 271 for each
Alela list, 176 for Camellia, and 102 for Talrand. Naively extending 14-candidate batches would take
roughly 8–20 calls per deck: around 2–5 minutes serially and a few cents to about $0.10, before extra
verification or retries. This is extrapolation, not a measured full-feed run or latency guarantee.
It argues for background progress, incremental reuse, and explicit coverage rather than a blocking tab.

## 3. Reproducibility and checks

Files in this directory:

- `data-report.json`: measured counts, archive hashes, dates, timings, and examples.
- `quality-cases.json`: frozen synthetic decks, actual sampled card facts, and separate controls.
- `quality-results.json`: original outputs, token usage, timings, and original broad-label scores.
- `quality-summary.json`: offline recalculation excluding uninformative controls.
- `prompt.txt`: v1 prompt used; exported after the run from the unchanged prompt constant.

The original results were saved before the harness added prompt/hash/time provenance fields.
Those fields are now written for future runs; no claim is made that they existed at execution time.
Bulk archives and the full public catalog stay in ignored `backend/.cache/new-cards-spike/`.
A narrow gitignore exception retains only this selected diagnostic evidence, not bulk rehosting.

The quality CLI now executes the revised evaluator and writes `quality-v2-*` files; it no longer
regenerates these v1 artifacts. See the [follow-up report](quality-v2-report.md#artifacts-and-verification)
for v2 offline replay commands; the [v3 report](quality-v3-report.md) documents its separate CLI.
Do not use `--live` to replay a summary: all three experiment budgets have been consumed. The frozen v1 inputs/results remain available for offline comparison.

Scryfall exports and future model outputs can change; source hashes identify this specific run.
Downloading fresh bulk archives does not reproduce the original snapshot.
At the end of v1, scoped Ruff lint/format, ty checks, and **40 offline tests passed**. A deliberate oldest -> newest-date
mutation failed the first-release regression test and was reverted. A name/token collision was
reproduced with a failing test before repair. No production-feature tests were claimed.

## Required next changes before a production recommendation feature

1. Normalize main playable release dates separately from first observed/first promo dates. Keep
   unresolved previews explicit; do not fabricate a future-legality guarantee.
2. Persist face-aware card facts, including printed characteristics, and preserve identity by ID.
3. Bind model choices to short local candidate keys/enums and validate exact coverage. Never let
   free-form UUID copying decide which real card receives a recommendation.
4. Ground explanations in explicit trigger conditions, costs, support cards, and exact card text;
   test Food creatures, cast/enter distinctions, alternative equip costs, and ward ownership.
5. The [second bounded validation](quality-v2-report.md) is now complete: identity binding improved,
   but Strong explanations still contain rules errors. Do not treat the revised prompt as approved.
   A stronger-reasoning/model comparison with untouched holdouts needs separate authorization.
6. Expand evaluation to real user-approved decks, full recent pools, preview mechanics, partner
   commanders, constraints/pending changes, and useful false negatives before setting thresholds.

This spike establishes feasibility and exposes failure modes. It does not approve the full feature
for launch, implement a new recommender, or certify production migration/job/authorization behavior.

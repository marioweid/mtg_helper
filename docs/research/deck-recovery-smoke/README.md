# Yuna/Meren direct-model recovery — measured smoke test

## Now

**The four authorized calls are complete; no retries or further calls are authorized.**
The user wanted practical evidence before feature implementation, using familiar lists rather than
requiring perfect recovery. Exact recovery did not reach the proposed 20-30 target hits in any run.
Meren was close and its top-ranked cards had substantial overlap; Yuna overlap was weaker.

**Subsequent user feedback:** after inspecting all suggestions, the user judged them a solid base
and preferred Terra. They identified Beast Whisperer's cast-based draw in Luna/Meren as less useful
when creatures frequently return directly from the graveyard. This is positive qualitative utility
feedback, not a complete per-card rating or a change to the measured recovery scores. Terra is the
preferred candidate for the next experiment, not an approved production model change. The user's
remaining concern is continuous casual browsing and discovery of model-unfamiliar releases.

This is a baseline for model knowledge plus a short goal, **not proof of the shared search algorithm
or interactive workspace**. No production deck, application feature, model setting, or deployment
changed. Only evaluator code, fixtures, tests, and selected experiment artifacts were added.

## Setup

Started at **2026-10-07 15:52:34 UTC**. One request per deck/model, four total, no tools or retries.
The hidden Yuna/Meren lists were never supplied to the models. Each received exact commander facts
and the same short inferred strategy across both models. Prompt, schema, goals, source/fixture
hashes and settings were frozen before calls in [inputs.json](inputs.json).

See the [pre-run protocol](protocol.md). Original reference lists have 65 Yuna and 66 Meren
nonland targets. Commanders, Guiding Hydra sideboard, and land-front cards were excluded; spell-front
MDFCs were allowed. Original output ranks remain intact; invalids were not replaced.

## Results

| Deck | Model | Exact hits / 50 | Target recovery | Top-ten hits | Invalid/duplicate | Latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Yuna | Luna | 15 | 15/65 | 4/10 | 0 | 19.3 s |
| Yuna | Terra | 16 | 16/65 | 5/10 | 0 | 48.4 s |
| Meren | Luna | 19 | 19/66 | 7/10 | 0 | 19.7 s |
| Meren | Terra | 19 | 19/66 | 8/10 | 1 land | 23.0 s |

All four provider responses completed and returned 50 structurally valid entries. Terra/Meren
included **Bojuka Bog** despite the explicit nonland-only request; local validation excluded it
from hit scoring. No duplicate, off-color, or unresolved output was observed in these four runs.

Total usage: **1,658 input and 8,211 output tokens**, including provider-counted reasoning.
Conservative estimated API token cost: **$0.05960975**, below both the $0.2069265 reservation and
$0.50 authorization. This is not an invoice and excludes coding/review sessions.

The larger model recovered one additional Yuna target and no additional Meren targets. This small
sample does not establish that either model is generally superior. Terra was substantially slower
on Yuna; no latency percentiles or production guarantees follow from four observations.

## Useful signal, and where it falls short

Recovery was not merely generic staples:

- Yuna hits included **Branching Evolution, The Ozolith, Resourceful Defense, Kami of Whispered
  Hopes, Fathom Mage, and Herald of Secret Streams**. Luna also found Master Biomancer; Terra
  found Ozolith, the Shattered Spire, Gyre Sage, Inspiring Call, and Damning Verdict.
- Meren hits included **Viscera Seer, Yawgmoth, Birthing Pod, Spore Frog, Eternal Witness,
  Plaguecrafter, Victimize, and Living Death**. Terra also selected the supplied Animate Dead,
  Reanimate and Necromancy package near the top.

Yuna output leaned toward broad +1/+1-counter packages, with many off-list choices such as Hardened
Scales, Conclave Mentor, Doubling Season, and Cathars' Crusade. Meren off-list choices included
Ashnod's Altar, Fleshbag Marauder, Caustic Caterpillar, and other familiar sacrifice/recursion cards.
Some can be valid alternatives; **off-list does not mean bad**. Their actual usefulness has not been
rated by the user, so exact-match counts must not be called recommendation precision or accuracy.

A supplementary offline first-paper-date check against the hash-verified full printing export found
6/65 Yuna and 2/66 Meren target designs first observed after both models' documented 2026-02-16
knowledge cutoff. Neither model recovered any of those targets. This illustrates a coverage gap,
not a causal proof about model training; it does not explain the many missed older targets.
First observed paper dates are not the New Cards pilot's normalized regular-release dates.

## Explanation limitation

A spot-check found a definite source contradiction in Luna/Yuna: **Conclave Mentor** was described
as gaining life "when your creatures grow." Its supplied-source Oracle text gains life when
Conclave Mentor itself dies, equal to its power. Luna also described Kami of Whispered Hopes as
"proliferates growth"; its rules add an extra counter and provide power-based mana, not a printed
proliferate ability. The latter wording is ambiguous, not counted as a second certified error.

This was not a comprehensive human semantic review. No semantic accuracy percentage or exhaustive
rules-error count is claimed. Valid card identities and an appropriate card choice do not certify
the generated explanation.

## Decision

Do not present the requested recovery target as passed, merge models' candidate pools to inflate
hits, or tune/retry this protocol until the numbers look good. The Meren result is a useful near-target
signal; Yuna needs better discovery/specificity or user assessment of alternatives.

**No full builder rewrite yet.** Given the user's positive qualitative feedback, the next proposed
check is source-grounded discovery rather than trying to maximize exact recovery: can a browsable
local candidate pool and fact-fed assessment surface useful alternatives and model-unfamiliar
releases without depending on remembered names? Keep unassessed candidates visible and distinguish
local matches from AI-assessed fits. Further paid checks need new explicit authorization. Record
coverage and interpretation failures before choosing a shared production architecture.

The empty New Cards feed and reported lag remain separate, unreproduced bugs. These measurements
do not establish their causes or show that either is fixed.

## Artifacts and verification

- [protocol.md](protocol.md): authorization and scoring criteria written before execution.
- [inputs.json](inputs.json): exact prompt, requests, schema, hashes, settings, pricing/reservation.
- [results.json](results.json): original outputs, all four attempts, usage, model and timings.
- [summary.json](summary.json): locally resolved identities, original ranks and hit/error flags.

Before live execution, **55 offline tests passed with warnings treated as errors**, including 14
recovery checks and 41 existing assistant/evidence tests. Scoped Ruff lint/format and ty passed;
AST checks confirmed function-size and parameter bounds. The first parser test failed against its
stub before implementation. Tests cover hidden-answer separation, name/face collisions, duplicate/
invalid scoring, spend reservation, changed call plans, frozen inputs, pre-call checkpoints,
transport failure, and repeat-run refusal. Transport was mocked for these tests.

Astra independently reviewed the experimental guard/scoring path read-only before calls and found
no supported blocker. It did not rerun tests, independently verify provider acceptance/pricing,
review imported configuration/helpers, or certify MTG recommendation quality. The parent checked
current official pricing and inspected source/fixture facts.

From `backend/`, offline replay only:

```bash
uv run --no-sync pytest -q -W error tests/test_deck_recovery_check.py
uv run --no-sync python -m scripts.deck_recovery_check --summarize
```

The replay requires the preserved cached Oracle export. Existing results block paid reruns and
resume; do not delete them to reuse the exhausted authorization.

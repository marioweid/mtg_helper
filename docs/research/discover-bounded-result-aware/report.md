# Two-deck result: keep bounded setup, do not add refinement

## Verdict

**The bounded v3 contract worked in all four calls. The result-aware refinement did not improve
either deck and should not be adopted from this experiment.** Keep the fixed baseline setup.

This was a fresh current-production baseline and one complete replacement refinement per deck,
not a replay or repair of the previous failed Meren request. All four outputs passed exact catalog,
eight-choice budget, index, grouping and source validation without trimming, retries or repairs.
Four observations are not a production reliability estimate or a guarantee against other failures.

The assistant reviewed **49 distinct card/deck identities** covering all eighty top-twenty placements,
using alphabetical source-only packets. Quotes and complete grades were validated before computing
reference recovery or inspecting arm/rank mappings. These are the lead assistant's judgments on two
familiar regression cases, not independent human truth or unseen-deck validation.

## Oracle-text usefulness

| Top-twenty review | Yuna baseline | Yuna refined | Meren baseline | Meren refined |
| --- | ---: | ---: | ---: | ---: |
| Distinctive engine connections, 3 points | 9 | 7 | 19 | 18 |
| Explicit requested function, 2 points | 11 | 13 | 0 | 0 |
| Generic useful support, 1 point | 0 | 0 | 0 | 1 |
| Unestablished dependency, 0 points | 0 | 0 | 1 | 1 |
| Clearly off-plan, -1 point | 0 | 0 | 0 | 0 |
| **Weighted fit, maximum 60** | **49** | **47** | **57** | **55** |

These scores distinguish Yuna's explicitly requested creature ramp from counter-engine interactions.
They are not percentages, final deck balance, or claims that every engine card is equally strong.

### Yuna

The baseline is individually coherent but already ramp-heavy: eleven reviewed cards primarily fill
the requested acceleration function, and several engine fits also produce mana. Refinement increases
ordinary ramp's share to thirteen, rather than strengthening the counter engine.

It removes **The Great Henge, Avenger of Zendikar and Snakeskin Veil from the entire matching pool**,
not just the top twenty. It promotes Avacyn's Pilgrim (previous rank 21), Arbor Elf (26) and Incubation
Druid (30), all already baseline matches. Incubation Druid is an excellent actual counter-to-mana
connection, but exchanging three engine cards for it and two ordinary ramp alternatives is not an
overall improvement under the predeclared rubric.

Useful source-based distinctions in the full ratings:

- Incubation Druid explicitly produces three mana when it has a +1/+1 counter; Yuna can supply that
  condition without paying adapt. This is more distinctive than simply putting counters on an Elf.
- Kami of Whispered Hopes and Selvala convert counter-grown power into mana. Selvala's draw can
  benefit opponents and is conditional, not automatic controller-only draw.
- Fanatic of Rhonas needs power four for its large mana mode. Its own printed power one plus Yuna's
  two counters is only three; another source of growth or another large creature is still needed.
- Faeburrow Elder's color-based stat boost is not counters. The Ozolith's preservation is creature-
  specific, whereas Yuna's graveyard redistribution can apply to another counter-bearing permanent.

The model made the broad counter-giving query require **`counters-matter` as an additional AND**:
that search shrank from **1,577 to 282** matches. Counter enablers and protection need not also carry
a counter-payoff classification. The smaller count excluded clearly useful source-text effects.
It left the **292-card mana-dork search unchanged**, letting ordinary ramp occupy the vacated ranks.
No ranking weight changed: only the filter changed.

### Meren

The baseline mostly finds genuine sacrifice/recursion value. Both versions retain **Mirkwood Bats**,
which was graded conditional: it cares about token creation/sacrifice, while Meren and the brief
do not themselves establish a token/Treasure package. Other suggested cards are not already present
support. A possible package is not proof the card is bad, but it is also not unconditional fit.

Refinement removes **Skullclamp, Solemn Simulacrum, Pitiless Plunderer, Morbid Opportunist, Syr Konrad
and Enduring Vitality from the entire matching pool**. It promotes Rise of the Dark Realms,
Blasphemous Edict, Dread Return, Grave Pact, Carrion Feeder and Torment of Hailfire from baseline
positions 21–30. Five additions have real engine connections; Torment is a generic finisher rather
than a reward for the controller's creature recursion. The new set is not nonsense, but it loses
useful draw/mana/death-value diversity and does not repair the token dependency.

Mechanically, it replaces **`death-trigger OR death-trigger-self` (797 matches)** with
**`blood-artist-ability` (30 matches)** and keeps the other five searches unchanged. That substitutes
one kind of death reward for the broader category, dropping draw, mana and graveyard-movement
payoffs that fit this value-oriented strategy. Mirkwood Bats survives through the unchanged
`your-sacrifice-matters` search, so narrowing the death-payoff lane does not remove that dependency.

The detailed review also preserves important limitations: Braids does not let Meren select a newly
sacrificed creature as the target of her already-triggered end-step ability; Living Death does not
return creatures sacrificed during its own resolution; Disciple of Freyalise has an eligible spell
front, but not simultaneous access to its land back; Enduring Vitality's self-return makes it a
noncreature enchantment rather than an endlessly reusable creature. Expensive recursion cards were
not rejected on an invented pace or budget restriction.

## Exact reference recovery — separate from usefulness

| Recovery metric | Yuna baseline → refined | Meren baseline → refined |
| --- | ---: | ---: |
| Reference hits in first 10 | 2 → 3 | 5 → 5 |
| Reference hits in first 20 | 4 → 5 | 12 → 11 |
| Reference hits in first 50 | 10 → 11 | 21 → 18 |
| Reference identities in full matching pool | 34/65 → 27/65 | 32/66 → 21/66 |
| Baseline-reachable identities retained | 27/34 = **79.4%** | 21/32 = **65.6%** |
| Matching pool size | 1,855 → 676 | 1,513 → 801 |

Neither refined pool recovered a new reference identity beyond its baseline-reachable set. Yuna's
slightly better first-page exact recovery therefore coexists with losing useful engine cards and
seven reachable reference identities. This is why list recovery is not recommendation precision.

Both adoption gates fail: weighted fit does not improve and reference retention is below the
predeclared 90% guard. Off-plan counts do not increase, but that alone is insufficient. The verdict
does not depend only on small subjective score margins; both pool-level coverage guards fail too.

## What the refinement actually saw

It received actual baseline counts, each search's first/second/middle/penultimate/last public facts,
and the combined top ten, with no evaluator grades or target-overlap information. In particular,
The Great Henge/Avenger were the counter-giving search's leading samples; Skullclamp/Solemn were
the death-payoff search's leading samples. Beneficial examples were therefore visible before the
model narrowed them away. Availability of result facts alone did not make this one-shot model
revision reason correctly about preserving valuable complementary effects.

This is evidence against **this prompt/model/sample/refinement procedure**, not proof that every
result-aware method fails. Do not tune constraints after this result and call the same two decks
an unseen confirmation. Any future idea needs a separately frozen comparison and held-out cases.

## Calls and verification

| Attempt | Valid | Provider seconds | Conservative estimated USD |
| --- | --- | ---: | ---: |
| Yuna baseline | Yes | 9.81 | $0.005914 |
| Meren baseline | Yes | 9.29 | $0.006211 |
| Meren refined | Yes | 9.65 | $0.008047 |
| Yuna refined | Yes | 8.88 | $0.007463 |

Exactly four attempts, no retries or paid per-card assessments. **98,942 input / 2,415 output tokens**,
**$0.027635** conservative estimated total, no unknown-cost attempt. The extra refinement requests
add about 18.53 provider seconds across the two decks and $0.015510 estimated cost. Neither the
extra latency nor the smaller pools produced a measured quality advantage here.

The two source menus, commander facts, publication/ranking fingerprints, grouped eligibility and
production popularity ordering were frozen. Reference identities entered scoring only after the
grades were complete. Source reads and post-grade SQL diagnostics used read-only isolated Compose
transactions. No saved strategies, physical cards, pending plans, product code or deployment changed.

Forty-two scoped offline safety/contract checks, Ruff lint/format, ty and function bounds passed
before spending. The current contract had already passed 138 affected checks. See
[verification.md](verification.md) and the [pre-call protocol](README.md).

## Evidence and reproducibility

- `inputs.json`: exact v3 baselines, source/code/ranking/fixture bindings, rubric and bounds.
- `requests/`: four exact checkpointed requests, including both refinement observation packets.
- `attempts.json`: four original provider outputs/usage/receipts and frozen ordered local pools.
- `review-packet.json`: alphabetical Oracle-fact packets without arm/rank/reference membership.
- `ratings.json`: forty-nine complete source-quoted lead grades, written before recovery inspection.
- `results.json`, `graded-results.json`: separate recovery and usefulness/adoption accounting.
- `diagnostics.json`: read-only per-query counts and exact top-twenty additions/removals, proving
  the removed engine cards are absent from the refined pools rather than merely below rank twenty.
- `manifest.json`: hashes of the frozen protocol, requests, receipts, grades and final results.

The exclusive ledger forbids rerunning `--live`; use local replay/grade commands only. Earlier
experiment artifacts remain untouched. **Recommendation: retain v3's contract fix and baseline;
do not add this extra refinement step or specificity-driven AND narrowing.**

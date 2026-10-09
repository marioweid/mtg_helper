# Luna refined-pipeline results

## Outcome

The six-request authorization completed once, no retries, no stopped/unknown-billing requests.
Estimated spend: **$0.03395705**, below the $0.1355 reservation and approved **$0.25 cap**.
The authorization is consumed; remaining dollars do not authorize extra calls.
No application integration, production model/data changes or deployment occurred.

- [Protocol and boundaries](protocol.md)
- [Frozen initial inputs, prompts and schemas](inputs.json)
- [Raw six responses/usage](results.json)
- [Automated summary](summary.json)
- [Actual four plans and all assessments/rankings](outputs.md)
- Exact requests and separate observations: `requests/` and `observations/`.

## Measured comparison

Same 64 candidate identities/facts per commander, but this pipeline adds a revision, source
prefixes, retrieved rules, revised-plan context and a closed coverage schema. It is **not** a
single-variable ablation or a pure model comparison. Old Luna had four calls; this run had six.

| Case | Original Luna grounded rows | Refined Luna grounded rows | Review time | Review cost |
|---|---:|---:|---:|---:|
| Meren | 61/64 | **63/64** | 48.10 s | $0.01113530 |
| Saheeli | 55/64 | **59/64** | 58.26 s | $0.01400745 |
| Combined | 116/128 (90.6%) | **122/128 (95.3%)** | — | $0.02514275 |

Both reviews assessed every supplied C-key exactly once, with no decorated ranking IDs or missing
candidates. Full literal validation still failed: Meren's Doubling Season quotation; Saheeli's
Fantastic Bounce, Fabrication Module, Evolution Sage/R02, Black Widow and Izzet Generatorium.
All 15 Meren rankings validated; 13/15 Saheeli rankings validated. Invalid ranked evidence is not
silently repaired. Paraphrased wording, omitted parentheticals, wrong-source quotations and invented
JSON-field quotations remain visible in raw outputs and `outputs.md`.

| Phase | Meren time / estimate | Saheeli time / estimate |
|---|---:|---:|
| Initial plan | 6.89 s / $0.00075805 | 15.57 s / $0.00199650 |
| Revision | 12.93 s / $0.00185390 | 13.73 s / $0.00420585 |
| Assessment | 48.10 s / $0.01113530 | 58.26 s / $0.01400745 |

The old four Luna requests cost $0.02563255. This six-call run cost about 32.5% more; it does not
establish a cheaper or uniformly faster end-to-end workflow. Grounding is output conformance,
**not semantic accuracy**. Meren/Saheeli are discussed regressions, not holdouts.

## Discovery/feedback evidence

- **Meren initial plan was not usable**, despite provider completion and schema validity. Four
  ordinary intents were followed by syntax-like intent strings, while all searches, nominations
  and rules queries were empty. Do not score it as a healthy initial planner. The one authorized
  revision produced an executable plan; this was not a retry or manually repaired output.
- Meren's replacement shortlisted 32 cards and independently admitted **3/13 diagnostics**:
  Viscera Seer, Sakura-Tribe Elder and Plaguecrafter. Two new queries still used literal `enters
  the battlefield` and returned **zero**. They were not executed until after the only revision;
  one feedback round cannot correct everything it introduces.
- **Neither Meren phase searched for counter modifiers/proliferate.** Later assessment recognizes
  Yawgmoth, Cankerbloom and Evolution Sage from supplied candidate/rules facts; those findings must
  not be credited as independent discovery. The revised outlet query excludes text saying only
  `Sacrifice another creature`; purpose prose saying untapped/no-tap does not enforce that property.
- Saheeli's initial entry query matched **zero**. Its revision used `enters` and matched **1,374**.
  This is working source-language correction, not proof of strategic admission recall.
- Saheeli actually requested and received subsequent rules pages for token/copy, entry/copy and
  end-step timing, proving the continuation field was used in model output and executed locally.
- Saheeli initial shortlist: 31 cards, **4/16 diagnostics**. Replacement: 31, **3/16 diagnostics**.
  Dropping Brudiclad loses its independent admission credit; it remains in the fixed assessment
  pool only because it was previously present. Do not silently union the plans to hide that loss.
- Revised Saheeli queries still span 469–2,394 matches in several lanes. Small hash-sampled
  admission over such broad pools remains a recall limitation, not complete discovery.

These diagnostics include conditional/negative fixtures and are **not precision or win scores**.
Native rules lookup is unclassified full-source access, not a guarantee of indirect reasoning.

## Targeted interpretation inspection

Against printed source facts and the existing official rules, useful explanations include:

- Meren's three proliferate assessments connect experience counters and note existing-counter
  prerequisites for Cankerbloom/Evolution Sage; Beast Whisperer distinguishes casting from direct
  returns. Those explanations do not change their discovery provenance.
- Saheeli Sundial identifies ending the turn after the delayed sacrifice is on the stack. Wurmcoil
  correctly describes a temporary 5/5 copy producing death tokens. Mirage Mockery states the
  additional three-mana entwine cost rather than the earlier five-mana error. Shuri's copy ability
  remains sorcery-speed rather than being accelerated by haste.

Supported remaining errors:

- **Meren/Doubling Season:** says it improves experience growth. Its counter replacement applies
  to permanents, not counters on players; experience counters therefore are not doubled.
- **Saheeli/Sai:** still claims four total mana for drawing. Printed activation is **{1}{U}**.
- **Saheeli/Second Harvest:** says four green mana; printed cost is **{2}{G}{G}**.
- **Saheeli/Decoction Module:** proposes recycling creatures for repeated entries, including
  Saheeli token copies. A token leaving the battlefield cannot return/re-enter (rule 111.8) and
  ceases to exist in the other zone (704.5d); bouncing a token is not reusable entry value.

Other imprecise or abbreviated explanations are not automatically counted as contradictions.
This is a targeted inspection, not exhaustive semantic certification or a semantic-accuracy rate.

## What this establishes / next refinement

Closed IDs/coverage and model-used query/rules feedback work in this bounded regression. They do
not establish a grounded application-ready recommender. Keep the pipeline separate and use Luna
for the next refinement rather than immediately launching another model comparison.

Priorities: operational plan validation beyond JSON shape; final-query feedback before declaring
search success; narrower/sustainable admission from broad matches; source-bound citations that
avoid fragile verbatim reproduction without weakening semantic checking. Keep visible per-item
failures/uncertainty. Do not hardcode Meren–proliferate or a universal per-card interaction schema.

After improving those boundaries, add an unused strategy and complete declared release enumeration,
then freeze the same improved protocol for other models. Any additional paid requests need new
bounded permission; **never delete `results.json` to rerun**.

## Verification

135 scoped offline tests passed, Ruff lint/format and `ty` passed. A deliberate relaxation of the
running budget guard made its regression fail before restoration. Independent read-only pre-live
review found no supported spending/input-boundary blockers; it did not certify Magic judgments or
provider acceptance. All old experiment JSON remained byte-identical after offline replays.

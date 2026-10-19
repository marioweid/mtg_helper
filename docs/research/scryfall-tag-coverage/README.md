# Scryfall-only labels: local coverage and admission check

## Now

**Source feasibility is promising; recommendation accuracy and production replacement are unproven.**
The user chose Scryfall as the only global label source, replacing local rules, MTGJSON and
Moxfield/Archidekt card labels. Their deck-local manual categories stay. This checkpoint implements
and runs the offline comparison only, not that migration. The next implementation boundary is in
[the replacement plan](../../scryfall-only-label-migration-plan.md).

No paid model calls, production schema changes, label imports into PostgreSQL, or application
cutover occurred. Local Compose PostgreSQL was started; its existing card count was read. Its schema
predates Discover snapshots, so application data was not upgraded or retagged for this experiment.

## Frozen method

- Fresh public Oracle Cards and Oracle Tags exports, both from October 12, 2026. Exact download URLs,
  timestamps and compressed SHA-256 values are in [protocol.json](protocol.json). Large gzip archives
  stay in ignored `backend/.cache/scryfall-tag-coverage/`.
- The current source catalog and existing source eligibility/identity functions are shared by arms.
- Reuse the preserved Yuna/Meren revised plans, including their original nominations. These are
  **regression decks**, not unused holdouts or newly generated plans.
- Baseline: current eight literal searches. Experimental arm: retain the first six searches and
  replace the final two with predeclared Scryfall queries. Each lane samples at most eight cards;
  query lanes share twenty positions; nominations and queries share at most thirty-two positions.
  Deduplication can leave fewer than thirty-two cards; no filler or replacement slots are added.
- Yuna label lane: creature scope, `mana-dork` AND (`gains-pp-counters` OR `gives-pp-counters`).
  Meren label lane: creature scope, `sacrifice-outlet-creature` AND `draw-engine`.
- Both use a second lane of `repeatable-proliferate` OR Scryfall's printed `Proliferate` keyword.
  This is a combined tag/printed-keyword hypothesis, not a tag-only ablation. Membership queries
  resolve source UUIDs and include hierarchy descendants; inherited membership is not a direct tag.
- These search hypotheses were selected by the parent from commander facts/goals and known prior
  failures, not produced by the production planner. Tag slugs/descriptions were inspected before
  outcomes. The protocol was frozen before scoring, but this is not a blind preregistration.
- Ten deterministic paired sampling seeds, not ten independent decks or model trials. Actual pools,
  query counts, samples, errors and reference overlap are preserved in [results.json](results.json).
- Reference lists are resolved for scoring only after independently constructing every candidate
  pool. No answer identities are supplied to the admission algorithm. The parent already knows the
  lists; this does not make their manually selected hypotheses independent of earlier research.

## Coverage

| Scope | At least one direct Oracle tag | Denominator |
| --- | ---: | ---: |
| Paper, currently Commander-legal nonland identities | 29,800 (99.36%) | 29,993 |
| Yuna eligible nonlands | 17,052 (99.32%) | 17,168 |
| Meren eligible nonlands | 11,574 (99.22%) | 11,665 |
| Yuna reference nonlands | 65 | 65 |
| Meren reference nonlands | 66 | 66 |

The export contains 4,577 tags. **Any-tag coverage is not useful-role coverage or label correctness**:
Oracle tags include set-cycle, flavor and other incidental metadata. Of 193 untagged legal nonlands,
178 have no supplied Oracle rules text and fifteen do. The latter include Slime Molding, Gloomwidow,
Armory Mice and Rusted Sentinel. Full names are in [inspection.json](inspection.json). Missing tags
must not exclude a card from literal/name discovery. This does not measure complete new-release
coverage: Oracle export printing dates are not independently verified first-design dates.

## Paired admission results

| Regression case | Mean admitted reference hits: baseline -> Scryfall | Pool sizes | Full matched reference identities: baseline -> Scryfall |
| --- | --- | --- | --- |
| Yuna | 6.3 -> 6.3 | baseline 31-32; Scryfall 30-32 | 26 -> 26 |
| Meren | 6.2 -> 6.5 | both 31-32 | 35 -> 26 |

Yuna tied on all ten seeds. Meren gained one admitted reference hit on three seeds and tied on seven.
**This is not evidence of improved relevance or rules correctness.** In particular, Meren's broader
matched reference coverage fell even while sampled admissions improved slightly.

The replacement lanes are smaller: Yuna's final baseline lanes matched 66/459 cards, replaced by
28/71. Meren's final baseline lanes matched 90/3,660, replaced by 50/43. Each lane remains truncated.
The average gain/loss per pool is Yuna 3.6/4.0 cards and Meren 3.9/4.0; duplicates explain unequal
sizes. Averaged genuinely new discoveries admitted were 1.1 for Yuna and 1.0 for Meren; other gained
admissions were already reachable by baseline queries/nominations. [discovery-attribution.json](discovery-attribution.json)
separates these cases instead of crediting every new shortlist entry as a new discovery.

Seed zero examples, not ranked recommendations:

- Yuna gained Kiora's Dambreaker through new discovery; Jugan Defends the Temple, Torgal and Arcbound
  Ravager were previously reachable matches newly admitted. Portcullis Vine, Blasting Station,
  Pteramander and Ishai were displaced. The lost sacrifice/evasion lanes may contain useful cards.
- Meren gained Atomize and Scheming Aspirant through new discovery; Ahriman and Spark Reaper were
  previously reachable matches newly admitted. Tenacious Dead and other options were displaced.

No final ranker was run. Source facts for every changed candidate and selected diagnostic examples
are preserved in `inspection.json`; a full human usefulness review remains outstanding.

## Narrow source inspection

- **Tender Wildguide:** Scryfall includes `mana-dork` and `gains-pp-counters`; the old local classifier
  missed its natural-language mana ability. These labels still do not say counters scale its output.
- **Cankerbloom:** lacks `repeatable-proliferate` in this snapshot (its sacrifice is one-shot), but
  the printed Scryfall keyword admits it to the modifier lane. No synthetic label is assigned.
- **Evolution Sage:** has `repeatable-proliferate`; its landfall ability supplies the concrete link.
- **Grim Haruspex / Beast Whisperer:** both have `draw-engine`; source labels additionally distinguish
  `death-trigger` versus `cast-trigger-you`. These are useful distinctions, not unconditional fits.
- **Doubling Season:** has `counter-doubler`, but its Oracle text limits that clause to permanents.
  Tag matching does not establish energy/experience-counter doubling on players.
- **Body Snatcher:** has `reanimate-creature`, but source text still exiles itself on its death ability.
  A recursion label cannot certify repeatable Meren recursion.

## Decision and remaining gate

Proceed with designing a **single Scryfall-backed global label catalog**, not a local classifier or
permanent fit ontology. Retain exact source facts and unlabeled discovery channels. This source
checkpoint does not justify adopting these fixed two-lane replacements as the production algorithm.

Before recommendation cutover, the planner must select valid tag IDs from the actual catalog using
commander facts and the editable goal, retain query/error provenance, and receive the same final
assessment budget. Check genuinely unused strategies and blind-review useful admissions, displaced
cards, ranked usefulness and material rules errors. Any paid evaluation needs separate permission;
old authorizations remain exhausted. Do not market tag coverage or reference overlap as accuracy.

## Independent Astra check

Astra reviewed this bounded checkpoint read-only and replayed the cached comparison in memory.
Results, inspection facts and discovery attribution matched the frozen artifacts exactly; source
hashes, hierarchy, budgets and numerical claims matched. **No blockers for the research gate.**
The verdict does not approve production migration or recommendation cutover. Astra reiterated that
changed intentions/selectivity and manually chosen regression hypotheses do not isolate tag quality
or establish automatic-planner improvement. No additional model evaluation or database call occurred.

## Historical reproduction and checks

The evaluator, regression-plan inputs and replay commands were kept in a separate
`research/commander-core-improvement` checkout at this checkpoint. That executable admission harness
is not included here; this repository preserves its frozen findings, not a runnable reproduction
of that experiment. Exact replay would also require the ignored bulk archives matching the
URLs/hashes in `protocol.json`. The ordinary publication/parser tests remain available here.

Historical scoped result: **35 tests passed**, lint and types passed. A deliberate transitive-hierarchy
mutation made its behavior test fail; restored code passes.

A broader Docker-backed run including `tests/test_tag_service.py` had **126 passed, one failed**:
`test_sacrifice_alone` expects no `aristocrats` tag, while the existing classifier adds it whenever
sacrifice appears. Both classifier and legacy test are byte-unchanged relative to HEAD. This
pre-existing discrepancy is documented, not repaired in a research slice that proposes retiring
the classifier. PostgreSQL integration setup succeeded; this was an assertion failure, not a missing
Docker/database error. These results do not claim the full repository suite passes.

# Discover relevance recheck: Yuna and Meren

**Follow-up:** the user-authorized four-call test is complete; see
[role-search experiment results](role-experiment/README.md). Richer term coverage helped, but
the tested equal-role ordering should not ship. All application behavior remains unchanged.

## Outcome — October 29, 2026

**The relevance concern reproduces. Do not enable a strong-only filter as the fix.**
The currently saved local Yuna criteria produce just 13 eligible matches and **zero** hits from
its 65-card nonland reference list. No Meren strategy is saved locally; the paired comparison
below uses explicitly manual, fixed role criteria for both decks, not newly generated AI terms.
The saved Yuna prose is "Creature-Cast Development", not the same text as the historical
counter-growth/redistribution brief; saved-strategy reproduction and paired role tests are distinct.

### Paired recovery results

| Fixed criteria / ranking | Yuna hits in first 50 | Yuna targets anywhere in pool | Meren hits in first 50 | Meren targets anywhere in pool |
| --- | ---: | ---: | ---: | ---: |
| Manual supporting roles, current OR/count/alphabetical ranking | 5 | 42/65 (2,376 matches) | 2 | 40/66 (2,211 matches) |
| Same criteria, strong/very_strong tag memberships only | 2 | 8/65 (133 matches) | 1 | 1/66 (25 matches) |
| Remove standalone generic mana-dork/draw-engine criteria | 4 | 36/65 (2,108 matches) | 0 | 35/66 (1,594 matches) |
| Original supporting roles, global popularity tie-break only | 5 | 42/65 (unchanged pool) | 8 | 40/66 (unchanged pool) |

The first three arms all have zero reference hits in their first ten. The popularity tie-break
gets one in each deck's first ten. These are **reference overlap**, not relevance precision:
off-list cards such as Bristly Bill, Hardened Scales or Priest of Forgotten Gods can be worthwhile.
None of these simple variants reaches the historical 20-hit smoke target. Two familiar regression
decks do not establish generalization, and these manually selected terms are not a production fix.

### Findings

1. **The bounded term menu is missing supporting roles before the AI can select them.**
   `source_terms()` ranks tags by trigram similarity of label/description/aliases against the
   entire strategy prose and keeps 80. For the saved Yuna prose, none of the seven checked role
   tags is offered: mana-dork, gains/gives-pp-counters, pp-counters-matter, counter-doubler,
   repeatable-pp-counters, repeatable-proliferate. Even the short historical Yuna brief offers
   only repeatable-pp-counters. Meren's brief offers sacrifice-outlet-creature and
   reanimate-creature, but not death-trigger, draw-engine or mana-dork.
2. **Saved Yuna criteria describe its own mechanism, not its complementary engine.**
   The saved Oracle tag is mana-ability-with-extra-effect and its keyword is Grand Summon.
   The latter occurs on Yuna alone in the measured source; commander exclusion removes that
   only match. The remaining 13 include Scaled Nurturer, Altar of the Pantheon and the three Bant
   Talismans. The Great Henge is also present: zero exact recovery does not mean every result is bad.
   Tightening those two criteria cannot discover the missing counter engine.
3. **Source membership strength is not strategic fit, and is mostly unspecified beyond median.**
   Of 238,569 direct assignments, 237,940 are median, one strong, and 628 very_strong. Filtering to
   strong/very_strong discards about 99.7% of direct assignments. The relevant source tags on
   Gyre Sage, Kami of Whispered Hopes, Viscera Seer, Plaguecrafter and Yawgmoth are median.
   Printed keywords have no strength field; that arm still admits their matches without filtering.
4. **Raw overlap count buries complementary engine pieces.**
   With fixed role terms, Incubation Druid is at rank 57, Kami of Whispered Hopes at 808,
   Yawgmoth at 221 and Viscera Seer at 2,097. Multiple related counter tags can reward the same
   mechanic repeatedly, while an important specialized card matches only one role. Alphabetical
   ties add further arbitrariness. Global popularity tie-breaking helps Meren but not Yuna's
   top-50 recovery; changing only the tie-break is insufficient.
5. **Commander facts are loaded but not supplied to the term-selection request.**
   `RecommendationService.suggest_terms()` stores commander facts in context, but
   `terms.Workflow.payload()` sends only strategy prose, source-tag identities/labels and printed
   keywords. Tag descriptions used for lexical retrieval are also absent from the model payload.
   This is a confirmed information-path limitation, not a measured claim that adding facts alone
   will fix recommendations. Existing tests check valid identities and lifecycle, not MTG utility.

### Recommended next experiment, not an implemented behavior change

- Repair strategy-to-source-term coverage first, including complementary roles and the commander
  facts/descriptions already available locally. Add quality checks for missing useful source roles.
- Compare small complementary role lanes, with intersections **within** a lane where needed
  (for example, counter-related mana creatures or death-triggered draw). Do not require every card
  to match every role; separate sacrifice outlets, recursion, support and payoffs must remain viable.
- Compare role-aware/diversified ordering against the preserved OR/count baseline rather than
  counting correlated tags as independent strategic evidence. Global popularity, if considered,
  must remain labeled as popularity rather than commander-specific synergy.
- Keep all-strength source assignments. Do not replace the current behavior with either the
  strength-only filter or the manually chosen fixture-specific criteria from this experiment.
- Rerun both known decks after a proposed fix, then test unused commander strategies and manually
  assess useful off-list alternatives. Fresh paid term-generation calls require new authorization;
  this check made none and did not reuse exhausted historical research budgets.

No application behavior, saved strategy, deck, schema, or model setting changed. The reproduction
remains intentionally red with `--check-saved`; this report is a diagnosis, not a fix claim.

### Verification and evidence

- `results.json`: source hashes/timestamp, source weight counts, actual retrieved menus, selected
  criteria, top-50 source evidence, full-pool reference ranks, and all popularity tie-break probes.
- Card source: `36c8c87fb0da4ff633cc29a79f8c5221d66f393bcc4e3bf365bd3de2f9168211`.
- Tag source: `1997cecccac98a5cdd4f1a3d861ec8bf6a3f5f658b9b2f6154b7521e8d432461`.
- Publication: October 28, 2026, 15:32:30 UTC; 39,099 card identities and 4,591 tags.
- Two consecutive baseline runs reproduced all recovery/pool counts. The command below with
  `--check-saved` exits 1: `Saved criteria below existing 20-hit recovery target: ['yuna']`.
- Docker-only scoped checks: **29 tests passed** (13 diagnostic checks and 16 existing Discover
  checks). Ruff lint, formatting, and ty pass for the added Python files. A temporary in-container
  mutation excluding rank 50 produced the expected scoring-test failure; unmodified tests pass.
- The diagnostic runner used read-only repeatable-read transactions; initial SQL inspection was
  SELECT-only. Integration tests used only disposable `mtg_helper_test`; no live database,
  startup maintenance or paid provider was used.

## Protocol (before measuring comparison arms)

- Use only the isolated Compose database, inside a read-only repeatable-read transaction.
  No startup maintenance, deck edits, schema changes, external data requests, or model calls.
- Run the current production Discover SQL, using an empty deck/owner identity for exclusions.
  This is hidden-list recovery, not the existing deck's already-owned-card feed. Commander,
  color, paper, current-source, and nonland eligibility remain the production conditions.
- Resolve the original Yuna/Meren main-deck fixtures for scoring only. Exclude commanders,
  sideboards and land-front cards; retain spell-front MDFCs. Unresolved/invalid entries fail.
- Record the saved criteria where available. There is a saved Yuna strategy, but no saved
  Meren strategy in this local database; do not label manually selected Meren terms as AI output.
- Preselect supporting role terms from the two historical strategy briefs, not target identities:
  see `ROLES` and `KEYWORDS` in `backend/scripts/discover_relevance_check.py`. These are informed
  regression hypotheses, not blind holdouts or a fresh end-to-end model evaluation.
- Compare unchanged OR/match-count ranking, the same terms with only strong/very_strong Oracle
  memberships, and the same terms without standalone generic mana-dork/draw-engine criteria.
  Printed keywords have no source strength; the strength arm leaves their behavior unchanged.
- Inspect the actual top-80 term retrieval for each brief and Yuna's saved strategy prose.
  Report whether the preselected supporting roles are available to the model at all.
- Report total pool, reference hits at 10/50, full-pool reference coverage, and card/evidence rows.
  Off-list cards are not automatically poor choices. No parameter tuning after seeing outcomes.
- The optional `--check-saved` reuses the historical **20 hits among 50 suggestions** smoke target;
  this is a red-capable recovery diagnostic, not a universal recommendation-accuracy gate.

## Invocation

From the repository root in PowerShell, after checking Docker and starting local PostgreSQL:

```powershell
docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --volume "${PWD}/docs/research/discover-relevance:/results" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --frozen python -m scripts.discover_relevance_check --output /results/results.json --check-saved
```

Requires the already-published local card/tag data; it never bootstraps or replaces it.
The resulting hashes identify the measured publication. The saved-Yuna recovery check is expected
to fail until its criteria improve; a nonzero exit does not mean the diagnostic failed to execute.

## Follow-up ranking probe (declared after the first three arms)

The first arms found 42/65 Yuna and 40/66 Meren reference cards somewhere in the role-term pool,
but only 5 and 2 among the first 50. Test one additional variable: retain eligibility, criteria,
and match-count-first ranking, but replace alphabetical tie-breaking with the already-stored
global `edhrec_rank` (missing values last). Do not fetch community data or change the application.
This is a diagnostic popularity prior, not commander synergy, an approved product change, or an
independent held-out evaluation. Preserve the alphabetical baseline and all earlier arms.

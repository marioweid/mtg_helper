# Commander Coach Suggestion Quality Plan

## Current Problem

The Coach pipeline now avoids copying Moxfield decklists, but suggestion quality is still not good enough.
Recent Camellia benchmark results:

- Top 2 Moxfield decks, remove 50 cards each.
- Moxfield used only to construct eval decks/removal sets.
- Agent itself does not query Moxfield.
- Exact recovery after weighted synergy scoring: 7/100.

This exact-hit score is expected to be lower without decklist copying, but the logs also show a real system issue:

- Deck Identity Agent often fails structured output validation.
- Cut Recommendation Agent often times out.
- Upgrade quality depends heavily on deterministic fallback behavior.

The next goal is not to copy Moxfield cards. The goal is:

> In 20 eval runs, at least 15 runs contain 4+ good suggestions.

A good suggestion means:

- legal in commander color identity
- not already in the deck
- not the commander/partner itself
- not generic ramp unless ramp is actually low
- connects to the deck identity or a weak synergy package
- has a clear deck-specific reason

## Phase 1 — Stabilize Identity and Cut Agents

### Issue

The Identity and Cut agents currently receive too much noisy deck context and fail too often. This weakens every downstream step.

### Work

1. Shrink Identity Agent payload.
   - Include commander/partner text.
   - Include archetype tags.
   - Include role budget summary.
   - Include synergy package summary.
   - Include only 15–25 notable cards, not full oracle text for every card.

2. Shrink Cut Agent payload.
   - Include identity report.
   - Include role budget.
   - Include synergy package report.
   - Include weak-card shortlist.
   - Include max 30 candidate cards.

3. Make deterministic fallback stronger.
   - For known tags like `food_matters`, `squirrel_tribal`, `aristocrats`, produce strong identity without LLM.
   - For Zaxara tags, produce X-spells/Hydra/big-mana identity.

4. Reduce output complexity.
   - Identity output should be short and stable.
   - Cuts output should rank fewer candidates with concise reasons.

### Success Criteria

- Identity Agent/fallback always returns useful archetype and preserve-themes.
- Cut Agent timeout rate is reduced.
- Eval logs no longer depend mostly on fallback behavior.

## Phase 2 — Improve Eval Metrics

### Issue

Exact Moxfield-card recovery is too narrow. A suggestion can be good even if it is not the exact removed card.

### Work

Extend `backend/scripts/eval_coach_suggestions.py` to report:

- exact hits
- good suggestions
- package hits
- role hits
- bad suggestions
- ramp spam count
- runs with at least 4 good suggestions

Good-suggestion scoring should reuse `synergy_scoring.score_card()`.

For Camellia, package hit examples:

- removed `Parallel Lives`, suggested another token doubler/token payoff
- removed `Peregrin Took`, suggested another Food/token/value engine
- removed `Mirkwood Bats`, suggested another death/drain payoff

For Zaxara, package hit examples:

- removed Hydra payoff, suggested another Hydra payoff
- removed X-spell, suggested another X-spell
- removed card draw, suggested another card advantage spell

### Success Criteria

- Eval output shows quality beyond exact-card match rate.
- We can track whether 15/20 runs contain 4+ good suggestions.

## Phase 3 — Add Final Selection Diversity Governor

### Issue

Even with better scoring, the top 10 suggestions can cluster into one package.

### Work

Add final selection rules before composing the Coach response.

For Camellia, target mix:

- 2 Food/Squirrel engines
- 2 token/sacrifice/death payoff cards
- 1 draw/value card if draw is low
- 1 interaction/protection card if low
- 0 ramp unless ramp is low

For Zaxara, target mix:

- 2 X-spells or Hydra payoffs
- 1 counter-scaling/big-mana payoff
- 1 card advantage spell if draw is low
- 1 interaction/protection card if low
- 0 ramp unless ramp is low

### Success Criteria

- Suggestions are diverse across weak packages.
- Ramp spam remains near zero when ramp role is `hold` or `trim`.
- At least 4 suggestions per run are judged good by eval in most runs.

## Phase 4 — Tune Synergy Scoring

### Issue

Current scorer improved theme specificity but still under-recovers premium package cards.

### Work

1. Add package-specific weights.
   - Camellia: Food/Squirrel/token packages outrank generic Aristocrats.
   - Zaxara: X-spells/Hydras outrank generic ramp.

2. Add negative filters.
   - Penalize generic sacrifice/graveyard cards that do not touch Food, Squirrels, tokens, or death payoffs.
   - Penalize lands unless mana-fix mode asks for lands.
   - Penalize extra ramp if role budget says ramp is fine.

3. Add positive boosts.
   - Boost cards that connect to 2+ packages.
   - Boost cards that overlap commander text.
   - Boost cards that fill both role deficit and synergy deficit.

### Success Criteria

- Camellia suggestions are consistently Food/Squirrel/token/aristocrats focused.
- Zaxara suggestions are consistently X-spell/Hydra/counter/value focused.

## Phase 5 — Iterate Against Benchmarks

Run these benchmark sets repeatedly:

```bash
uv run python scripts/eval_coach_suggestions.py --commander camellia --top-decks 5 --remove-count 10
uv run python scripts/eval_coach_suggestions.py --commander camellia --top-decks 5 --remove-count 30
uv run python scripts/eval_coach_suggestions.py --commander camellia --top-decks 2 --remove-count 50
uv run python scripts/eval_coach_suggestions.py --commander zaxara --top-decks 5 --remove-count 10
uv run python scripts/eval_coach_suggestions.py --commander zaxara --top-decks 5 --remove-count 30
```

Target:

- 15/20 runs have 4+ good suggestions.
- Average bad suggestions <= 1 per run.
- Ramp spam <= 1 per 10 runs when ramp is already enough.

## Implementation Order

1. Stabilize Identity Agent payload/fallback.
2. Stabilize Cut Agent payload/fallback.
3. Extend eval metrics with package/role/good-suggestion scoring.
4. Add final selection diversity governor.
5. Tune synergy weights with benchmark results.
6. Repeat eval until target is reached.

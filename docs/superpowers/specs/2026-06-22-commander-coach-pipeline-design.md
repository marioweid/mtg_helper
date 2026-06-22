# Commander Coach Multi-Agent Pipeline Design

## Goal

Refactor the Commander Coach so whole-deck advice is driven by focused specialist steps instead of one monolithic Deck Doctor pass. The first implementation should only add agents that create immediate value with the app's current data: deck identity, mana base, curve/tempo, cuts, upgrades, and final response composition.

## Scope

Build the MVP pipeline:

1. Deck Identity Agent
2. Deterministic Mana Base Step
3. Deterministic Curve & Tempo Step
4. Cut Recommendation Agent
5. Upgrade Finder Agent
6. Final Coach Response Composer

Defer decklist import, card normalization, rules/oracle validation, full synergy graph, and table-fit/bracket specialist work until the app has stronger supporting data and UI.

## Architecture

`commander_coach.orchestrator.run_coach()` remains the stable entrypoint. Internally it creates a shared deck profile and runs the pipeline sequentially. The public API remains compatible by returning the existing `CommanderCoachResponse` and `DeckDoctorResponse` shapes.

Pipeline:

```text
route request
→ build compact deck profile
→ identity_agent.identify_deck
→ mana_step.analyze_mana
→ curve_step.analyze_curve
→ cuts_agent.recommend_cuts
→ upgrades_agent.recommend_upgrades
→ Theme Guardian validation/filtering
→ final_response.compose_doctor_response
```

## Components

### Deck Identity Agent

Uses structured LLM output to answer what the deck is trying to do. It receives commander text, bracket, archetype tags, memory notes, user goal, and a compact card list. It outputs archetype, main plan, secondary plan, power target, tensions, and themes that recommendations must preserve.

### Mana Base Step

Uses the existing `mana_base_service.analyze_mana_base()` deterministic report. It summarizes land count, recommended lands, color deficits, risky cards, and ramp count. It does not need a separate LLM call in v1.

### Curve & Tempo Step

Uses `mana_curve_service.current_curve()` and simple Commander heuristics. It flags overloaded mana-value buckets, underfilled early buckets, low early ramp, and high-cost pressure.

### Cut Recommendation Agent

Uses structured LLM output. It can only recommend cards that exist in the deck. It receives identity, mana report, curve report, weak-card heuristics, and compact card rows. It ranks cuts by score and explains the deck-specific reason.

### Upgrade Finder Agent

Uses Pydantic AI tools and existing `card_search`. It searches legal additions constrained by commander color identity, current deck cards, identity, curve/mana needs, and cut roles. It only returns cards from tool results.

### Final Composer

Deterministically converts identity, mana, curve, cuts, and upgrades into the existing `DeckDoctorResponse`: summary, game plan, findings, cuts, adds, and swaps.

## Error Handling

Each step has a fallback so the Coach can still answer:

- Identity failure: derive a conservative identity from commander name, tags, and bracket.
- Mana failure: omit mana findings.
- Curve failure: omit curve findings.
- Cut failure: return no cuts.
- Upgrade failure: return no adds.
- Validation issues: reuse existing Theme Guardian revision/filter flow where possible, and filter invalid recommendations before returning.

## Testing

Unit-test deterministic mana/curve mapping and final composition. Mock LLM agents in Coach route tests to confirm the orchestrator calls the new pipeline and preserves response compatibility.

Add an evaluation-style test or script for a Camellia, the Seedmiser deck: remove 10 known cards from a high-synergy list, run the pipeline, and check that at least 6 removed cards are recommended back when the prompt asks to restore missing Food/Squirrel/aristocrats pieces. This should be a local evaluation helper rather than a brittle normal CI test if it depends on live LLM/database content.

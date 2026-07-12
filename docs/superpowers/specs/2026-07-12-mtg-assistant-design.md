# MTG Assistant Design

**Date:** 2026-07-12
**Status:** Approved for implementation planning

## Summary

Replace the Commander Coach multi-agent pipeline with one conversational MTG Assistant. The
assistant uses at most one language-model run per normal turn and selects compact, deterministic
tools for retrieval, legality, bracket evaluation, deck analysis, and synergy scoring. The model
interprets the request and explains verified results; it does not determine factual game or deck
constraints.

The initial implementation supports card recommendations, deck analysis, cuts and swaps, and the
existing memory/preferences behavior. Its boundaries also permit future Magic rules questions
without introducing specialist agents.

## Motivation

The current whole-deck request path can invoke a router plus identity, cuts, upgrades, and
challenger model runs. Each specialist repeats deck context and transforms prior model output,
which consumes many tokens without reliably improving recommendations. The upgrade specialist can
also make many broad card-search calls before validation removes unsuitable results.

The project already contains stronger foundations that should drive recommendations:

- Moxfield hub and Archidekt tag card statistics;
- shared, administrator-curated theme groups;
- deterministic role, curve, mana, legality, and synergy analysis;
- stored descriptions for source tags and theme groups; and
- structured user and deck preferences.

The new design makes those capabilities directly accessible through tools instead of surrounding
them with multiple reasoning agents.

## Product Model and Naming

The user-facing feature is **MTG Assistant**. It is a single conversational entry point that can
choose tools as needed. Users do not select or interact with specialist agents.

Existing Commander Coach API paths may remain as temporary compatibility aliases during migration.
New service names, UI text, telemetry, and documentation use MTG Assistant terminology. Compatibility
aliases must call the new path and must not retain the old specialist pipeline as a fallback.

## Architecture

One Pydantic AI agent receives the latest user request, a compact deck summary, relevant stored
preferences, and tool definitions. A normal turn permits one model run. The run may make several
deterministic tool calls within a strict request budget and then returns structured output that is
rendered to the existing response envelope.

```text
User request
    -> MTG Assistant (one model run)
        -> theme discovery
        -> theme-card retrieval
        -> deck analysis
        -> commander/deck synergy scoring
        -> legality and bracket evaluation
        -> future rules retrieval
    -> grounded response
```

The identity, cuts, upgrades, challenger, and Theme Guardian agents leave the active request path.
Useful deterministic functions currently located beneath those modules should be retained or moved
behind focused services. Model-produced intermediate reports are not preserved as architectural
boundaries.

Simple requests may bypass the model when the endpoint can answer them deterministically. This is an
optimization, not a requirement for the first migration.

## Tool Contracts

All tools return bounded Pydantic V2 models. They return the minimum evidence needed for reasoning,
not full database rows, full deck objects, or prewritten essays.

### `search_themes`

Inputs:

- natural-language query;
- optional maximum results, capped by the server.

Behavior:

- searches stable theme-group slugs, labels, descriptions, aliases, and enabled source tags;
- resolves phrases such as "X-spells", "variable mana", and "big X finishers" to the same theme;
- ranks shared groups before redundant source-level matches; and
- returns a small set of identifiers, labels, descriptions, aliases, confidence, and source
  coverage.

If no match is credible, the assistant asks one clarifying question. It must not compensate with a
broad, expensive card search.

### `find_theme_cards`

Inputs:

- one or more theme identifiers returned by `search_themes`;
- deck identifier or commander color identity;
- optional roles, budget, mana value, card types, excluded names, and result count.

Behavior:

- resolves shared groups to their enabled Moxfield and Archidekt members;
- ranks candidate cards using stored source synergy statistics;
- filters Commander color identity, format legality, novelty, and explicit constraints in SQL or
  deterministic application code; and
- returns compact candidate evidence, including source score, theme membership, role tags, price
  when available, and bracket/game-changer flags.

Source statistics are evidence for ranking, not permission to copy source decklists.

### `analyze_card_synergy`

Inputs:

- candidate card identifiers;
- deck identifier.

Behavior:

- measures commander-text interaction, selected-theme overlap, role contribution, existing engine
  support, redundancy, and known anti-synergies;
- returns individual signals plus a deterministic aggregate score; and
- does not ask a model to manufacture a score.

### `analyze_deck`

Inputs:

- deck identifier;
- optional requested focus.

Behavior:

- computes curve, land and mana-source counts, functional roles, selected-theme density, bracket
  signals, and clearly defined gaps;
- can identify weak-fit cut candidates using explicit signals; and
- returns bounded summaries and evidence lists.

For swap requests, the assistant compares retrieved additions with these deterministic cut signals.

### `check_deck_legality`

Inputs:

- deck identifier or bounded proposed card changes;
- format.

Behavior:

- checks current ban status, color identity, deck size, singleton restrictions, commander
  eligibility, companion restrictions, and other machine-readable format constraints;
- returns failures and evidence codes; and
- blocks affected recommendations when the check cannot complete.

Legality is never delegated to an LLM.

### `check_bracket`

Inputs:

- deck identifier or bounded proposed card changes;
- optional target bracket.

Behavior:

- applies versioned Game Changer lists and machine-readable bracket rules;
- separates illegal cards from bracket-impact warnings;
- returns the ruleset version and evidence that caused the result; and
- treats bracket output as guidance for pregame discussion, not format legality.

Lists and thresholds must live in updateable data or configuration, not prompts. Current rules must
not be reduced to a hard-coded "more than three Game Changers" heuristic.

### Future `lookup_rules`

The architecture reserves a rules-retrieval tool that searches versioned Comprehensive Rules,
official rulings, and card rulings. It must return source identifiers and distinguish official rules
from strategic interpretation. Rules support is outside the first migration unless explicitly added
to the implementation plan.

## Theme Metadata

Descriptions are first-class retrieval metadata. They teach the assistant when a theme applies;
card membership and ranking still come from deterministic data.

Each shared theme group should contain:

- a stable slug and display label;
- a concise description of the strategy;
- common enablers and payoffs;
- disambiguating exclusions where useful; and
- searchable aliases.

Moxfield hubs and Archidekt tags retain their source descriptions. When an ungrouped source tag has
no usable description, administrators may add an override or leave it searchable by label only. A
missing description must not be generated and persisted automatically by the assistant.

Prompt construction must not embed the entire theme catalog. `search_themes` retrieves only a few
relevant descriptions. Existing catalog APIs should expose descriptions where useful to the UI, but
large catalogs remain outside routine model context.

## Request Flow

For "Suggest strong X-spells for my deck":

1. The assistant calls `search_themes` with the user's phrase.
2. The tool resolves the request to the X-spells theme and returns its description.
3. The assistant calls `find_theme_cards` with the resolved identifier and deck constraints.
4. It calls `analyze_card_synergy` for a bounded shortlist.
5. It verifies candidate legality and bracket impact.
6. It presents grounded recommendations, their deck-specific reasons, and relevant warnings.

For cuts or swaps, `analyze_deck` supplies weak-fit slots before candidate retrieval. For a direct
legality question, the assistant calls only the legality tool. Mixed requests can call multiple tools
within the same model run.

## Token and Cost Controls

- One model run per normal conversational turn.
- A strict server-side request/tool-call limit lower than the current specialist aggregate.
- Explicit caps on theme matches, candidate cards, descriptions, evidence strings, and output
  tokens.
- Compact deck summaries and bounded recent conversation instead of repeated full deck payloads.
- No model-generated intermediate specialist reports.
- No full theme catalog in the system prompt.
- No automatic retry that starts a second independent agent pipeline.
- Tool-budget exhaustion returns useful verified results already obtained or a concise limitation.
- Telemetry records input, output, and total tokens; model requests; tool calls; latency; and result
  counts per turn.

The implementation plan must select concrete initial limits and make them configurable. The
acceptance target is one model run for ordinary recommendation, analysis, swap, and legality turns.

## Grounding and Safety Rules

- Every recommended card must originate from a retrieval tool in the current run.
- Every recommendation must pass deterministic legality validation before presentation.
- The assistant must not invent cards, theme membership, prices, rankings, or bracket rules.
- Tool outputs include stable card identifiers so validation does not depend on name parsing.
- Price and externally sourced facts include freshness metadata when available.
- Missing hub/tag statistics may fall back to local card tags and text retrieval only when the
  response labels the weaker evidence.
- A failed legality or bracket check prevents the affected recommendation rather than silently
  accepting it.
- Rules answers must separate sourced rules from advice or interpretation.

## Feedback and Preferences

The feedback loop remains but does not use a reviewer agent.

- Record accepted and rejected recommendations with deck, candidate, and timestamp.
- Capture structured reasons such as too expensive, too strong, weak theme fit, already tested, or
  disliked play pattern.
- Convert durable user statements into existing preference/memory structures.
- Apply preferences as retrieval filters or deterministic scoring adjustments on future turns.
- Recalculate deck and commander synergy after deck changes.
- Let the model explain the signals without changing their numeric values.

Global cross-user learning is excluded initially because it requires data-volume, privacy, and abuse
controls that are not necessary for this migration.

## Failure Handling

- Ambiguous theme: ask one focused clarification question.
- No theme statistics: use clearly labeled local fallback retrieval or report no grounded result.
- Tool timeout: retain verified partial results and state the limitation.
- Legality/bracket service unavailable: omit or block affected recommendations.
- Model failure: return a concise recoverable error; do not invoke the old pipeline.
- Invalid model output: validate with Pydantic V2 and allow only the bounded retry behavior chosen in
  the implementation plan.

## Migration

1. Introduce compact tool response models and services around existing deterministic functionality.
2. Add searchable theme descriptions and aliases without changing stable theme identifiers.
3. Build the single MTG Assistant agent with hard usage limits.
4. Route existing Coach requests through the new assistant behind a temporary compatibility layer.
5. Compare quality, grounding, tokens, tool calls, and latency with the existing pipeline using a
   fixed evaluation set.
6. Remove the specialist request path and obsolete prompts after the new path meets acceptance
   criteria.
7. Rename remaining product-facing Coach labels and retire compatibility aliases separately if API
   consumers need a deprecation window.

Existing deterministic modules may be refactored only where needed to expose clean contracts.
Unrelated deck-building or retrieval work is outside this change.

## Testing and Acceptance Criteria

Unit tests cover every deterministic tool, including empty results and failures. Integration tests
cover PostgreSQL theme resolution across shared groups, qualified Moxfield/Archidekt tags, and
ungrouped tags. Agent tests use a fake model to verify tool choice and grounded structured output.

The evaluation set must include:

- strong X-spells for a legal deck;
- ambiguous and unknown themes;
- color-identity and banned-card rejection;
- singleton and commander-eligibility failures;
- bracket-impact warnings using a fixed ruleset version;
- additions, cuts, and complete swaps;
- budget and disliked-card preferences;
- missing source statistics and local fallback; and
- mixed conversational requests that need more than one deterministic tool.

The migration is acceptable when:

- ordinary turns use no more than one model run;
- all presented card recommendations are traceable to retrieval output and pass legality checks;
- theme queries use descriptions and select the expected theme in regression fixtures;
- tool responses and model context obey configured size limits;
- token, latency, and grounded-quality evaluation beats the current Coach baseline; and
- no active request depends on identity, cuts, upgrades, challenger, or Theme Guardian model runs.

## Existing Technology

The backend already uses Pydantic V2 (`pydantic>=2.12,<3`) and Pydantic AI. New request, tool, and
response models should continue using Pydantic V2 conventions.

## External Design Signals

Public MTG assistants commonly separate deterministic deck-health or role analysis from a user-facing
explanation layer. LandFall AI describes deterministic recommendations and synergy-aware upgrades;
MTG Deck Tag classifies cards by functional role and compares counts with configurable templates;
Commander AI describes a persistent deck thesis used to filter choices. These are supporting product
signals, not dependencies or authoritative implementation specifications.

Commander legality and bracket data must follow current primary sources. Wizards' February 2026
Commander update states that brackets guide pregame conversations and can change independently from
format legality, reinforcing the need for versioned deterministic rules rather than prompt knowledge.

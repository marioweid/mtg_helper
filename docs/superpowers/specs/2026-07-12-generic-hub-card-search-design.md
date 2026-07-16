# Generic Hub-First Card Search Design

**Date:** 2026-07-12
**Status:** Implemented; Gemini 3.5 is the production default

The typed `search_cards` contract, hub-first filtering, unchanged-filter global fallback,
provenance, assistant grounding, and deterministic tests were implemented on 2026-07-16. The
production default changed to `gemini-3.5-flash` on 2026-07-16 after explicit operator approval.
The comparative intent suite remains recommended for measuring quality, token, latency, and cost
changes. All agents omit temperature for Gemini 3.5 while preserving `CHAT_MODEL` overrides.
Lightweight routing, extraction, description, and identity tasks use the configurable `FAST_MODEL`
(`gemini-3.1-flash-lite` by default); reasoning-heavy agents remain on `CHAT_MODEL`. Each agent also
sets the lowest explicit thinking level appropriate to its task.

## Summary

Replace theme-only card retrieval with a generic, typed card-search tool. MTG Assistant interprets
the user's language, selects relevant Moxfield hubs or Archidekt tags, and expresses card constraints
through reusable filter fields. The backend applies those constraints deterministically while
preserving hub/tag statistics as the preferred ranking signal.

No commander, theme, or query receives custom filtering code. The same tool must support thousands
of commanders and arbitrary combinations of themes, mana costs, card properties, prices, and deck
constraints.

The change also evaluates and adopts the stable `gemini-3.5-flash` model for improved structured
function calling, provided regression evaluations confirm acceptable quality, tokens, latency, and
cost.

## Problem

The first MTG Assistant implementation can resolve a phrase such as "X-Spells" to a shared theme,
but `find_theme_cards` only accepts theme identifiers, price, and coarse roles. The X-Spells hub may
include related lands, payoffs, or cards with variable effects that do not contain `{X}` in their
casting cost. The model then receives a broad candidate set and cannot recover the exact cards the
user requested.

Adding a hard-coded X-spell rule would fix one query but create an unmaintainable collection of
commander and theme exceptions. Hubs and tags should establish relevance; generic filters should
express the precise card properties requested by the user.

## Architecture

A thematic request uses two model-selected tools inside one assistant run:

1. `search_themes(query)` resolves natural language to shared theme groups or qualified source tags.
2. `search_cards(query)` searches the selected theme pool with typed structural filters.

The second tool performs filtering and ranking in one backend operation. It must not return a broad
list for the model to filter in context.

```text
User request
  -> MTG Assistant interprets intent
  -> search_themes("X-Spells")
  -> search_cards(
       theme_tags=["x_spells"],
       mana_cost_symbols=["{X}"],
       exclude_deck_cards=true,
       ranking="theme_synergy"
     )
  -> grounded explanation
```

The language model maps language to typed fields. SQL and deterministic application code enforce
those fields. Tool results remain the only permitted source of actionable card recommendations.

## Generic Search Contract

Introduce a bounded Pydantic V2 input model for card search. Initial fields are:

- `theme_tags: list[str]`: shared group slugs or qualified Moxfield/Archidekt tags returned by theme
  discovery;
- `mana_cost_symbols: list[str]`: exact normalized mana symbols that must occur in `mana_cost`, such
  as `{X}`, `{U}`, or `{2/W}`;
- `mana_value_min: float | None` and `mana_value_max: float | None`;
- `card_types: list[str]` and `subtypes: list[str]`;
- `oracle_text_all: list[str]`: every term or phrase must match normalized oracle text;
- `oracle_text_any: list[str]`: at least one term or phrase must match;
- `required_tags: list[str]` and `excluded_tags: list[str]` across supported local tag columns;
- `min_price_eur_cents: int | None` and `max_price_eur_cents: int | None`;
- `exclude_deck_cards: bool`, defaulting to true;
- `ranking`: a bounded enum such as `theme_synergy`, `commander_fit`, `popularity`, `price`, or
  `mana_value`; and
- `limit`, constrained by a small server-side maximum.

Commander legality and color identity are mandatory server-side filters rather than optional model
arguments. Unsupported or malformed symbols and contradictory ranges return structured validation
errors.

The contract is intentionally composable. For example:

- "X-spells" becomes `mana_cost_symbols=["{X}"]`;
- "cheap X-spells" adds `mana_value_max` only if the user provides or clearly implies a concrete
  bound; otherwise the assistant should ask what cheap means or omit that filter;
- "X-spell creatures" adds `card_types=["Creature"]`; and
- "X-spells under five euros" adds `max_price_eur_cents=500`.

No field is named after a commander or theme.

## Hub-First Retrieval

When `theme_tags` are present, the service resolves them to enabled Moxfield hubs and Archidekt tags
and forms the preferred candidate pool from stored card statistics. All structural filters are
applied in SQL before results are returned.

Surviving candidates are ranked with these signals, in order:

1. selected hub/tag synergy score;
2. deterministic commander-text and deck-theme overlap;
3. deterministic role or deck-gap contribution when available; and
4. general popularity as a tie-breaker.

The tool returns compact evidence:

- stable card identifier and display fields;
- matched hub/tag identifiers;
- hub/tag synergy score;
- matched structural filters;
- commander/deck signals;
- price and Game Changer status when available; and
- `evidence_source="hub_stats"`.

## Global Fallback

If the resolved hub/tag pool contains no cards after applying all filters, the backend repeats the
same structural search over the complete local card database. It continues to enforce Commander
legality, color identity, deck exclusions, and price constraints.

Fallback ranking uses commander/deck overlap followed by general popularity. Results include
`evidence_source="global_fallback"`. The assistant explicitly tells the user that the selected hub
contained no matching cards and that the displayed cards came from the complete legal database.

The fallback must not relax or remove any requested filter. It changes only the candidate pool.

## Intent Interpretation

The assistant system prompt and tool field descriptions teach the model to distinguish:

- mana cost from mana value;
- mana cost symbols from symbols appearing only in oracle text;
- card type from subtype;
- theme relevance from structural card requirements; and
- preferred hub membership from mandatory constraints.

The assistant should ask one focused clarification when a requested constraint cannot be expressed
unambiguously. It should not silently invent numeric thresholds or omit an explicit requirement.

For "Show me good X-Spells," the expected interpretation is:

```json
{
  "theme_tags": ["x_spells"],
  "mana_cost_symbols": ["{X}"],
  "exclude_deck_cards": true,
  "ranking": "theme_synergy",
  "limit": 8
}
```

Treasure Vault and Three Steps Ahead must not match because `{X}` is absent from their casting
costs. Cards containing `{X}` in `mana_cost` remain eligible even if their oracle text does not
spell out the letter X.

## Gemini Model Migration

The current default is `gemini-2.5-flash`. Evaluate `gemini-3.5-flash`, Google's stable generally
available Flash model, against a fixed tool-selection suite. Gemini 3.5 Flash supports function
calling and structured output and is recommended by Google for improved agentic and multi-step tool
use.

Migration requirements:

- keep the model configurable through `CHAT_MODEL`;
- retain or roll back the production default based on the post-migration evaluation;
- remove temperature from Gemini 3.5 model settings because Google no longer recommends it;
- test low and medium thinking levels, preferring the least expensive setting that meets quality
  criteria;
- confirm compatibility with the installed Pydantic AI Google provider and Google SDK before
  dependency upgrades;
- upgrade `google-genai` only when required by that compatibility test; and
- preserve current request, tool-call, and token limits.

The evaluation compares correct tool selection, correct filter arguments, grounded result quality,
input/output tokens, number of model requests, latency, and estimated cost. A newer model is not a
substitute for precise tool contracts.

## Errors and Grounding

- Unknown theme: ask for clarification or continue with global search only when the remaining
  structural constraints are sufficient and the user accepts that behavior.
- Invalid filter: return a structured tool error that identifies the field and valid form.
- No hub matches: run global fallback with unchanged filters and label it.
- No global matches: return an honest empty result and retain all user constraints.
- Database or legality failure: do not present affected recommendations.
- Ungrounded model output: discard any actionable card identifier not returned by the current
  search tool call.
- Tool budget exhausted: return verified partial results or a concise limitation.

## Testing

Unit tests cover normalization and SQL-filter construction for every field, including empty values,
invalid mana symbols, contradictory ranges, and combined filters.

Database integration tests cover:

- exact `{X}` in `mana_cost` versus X appearing only in oracle text or an activated ability;
- exact hybrid and phyrexian symbols;
- mana-value bounds;
- card types and subtypes;
- all/any oracle-text terms;
- included and excluded tags;
- price constraints and missing prices;
- Commander color identity and legality;
- exclusion of current deck cards;
- multi-source shared theme groups;
- hub-first ranking; and
- unchanged-filter global fallback.

Agent tests use fake models to verify that representative language maps to the expected typed
arguments. The suite includes X-spells, cheap interaction, creature-only payoffs, oracle-text
requirements, price limits, and mixed constraints.

Run the same intent suite against Gemini 2.5 Flash and Gemini 3.5 Flash. Record tool accuracy, model
requests, tokens, latency, and cost as a post-migration retain-or-rollback decision.

## Acceptance Criteria

- "Show me good X-Spells" resolves the X-Spells theme and requests
  `mana_cost_symbols=["{X}"]` without custom X-spell code.
- All explicit user constraints are enforced before cards reach model context.
- Theme selection narrows and ranks candidates but does not replace structural filtering.
- Empty hub results trigger the same-filter global fallback and are visibly labeled.
- Every actionable recommendation is traceable to a current search result.
- No commander-specific or theme-specific filtering branch is added.
- The explicitly approved Gemini 3.5 default is retained only if post-migration evaluation confirms
  acceptable tool-selection quality, tokens, latency, and cost.

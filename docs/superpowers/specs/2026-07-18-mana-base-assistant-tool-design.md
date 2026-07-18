# Mana-Base Assistant Tool Design

## Goal

Answer requests such as "Can we improve my landbase?" with a bounded, grounded mana-base
analysis. The common request must be answerable with one deterministic tool call, without
exhausting the assistant's cumulative token or tool-call limits.

## Architecture

Add an `analyze_mana_base` tool to the existing MTG Assistant. The tool delegates calculations
and candidate selection to the existing deterministic mana-base service rather than asking the
language model to infer deficiencies or invent replacements.

Keep `search_cards` as an optional second tool. It is used only when the user requests additional
alternatives or supplies constraints the deterministic analysis does not cover, such as a price
limit, preferred land cycle, or excluding fetch lands.

## Tool Contract

`analyze_mana_base` returns a compact validated model containing:

- current land count and the recommended range;
- required and available color sources;
- color deficiencies;
- tapped-land and utility-land pressure when available from the underlying analysis;
- grounded land-for-land swaps;
- a concise deterministic reason for each swap.

Every proposed removal must be present in the current deck. Every proposed addition must come
from the deterministic mana-base candidate service and include its database-backed card identity.
The response is bounded so one tool result cannot dominate the model context.

## Assistant Behavior

The system prompt directs requests mentioning `landbase`, `land base`, `mana base`, color fixing,
or land swaps to `analyze_mana_base` first. Its result is sufficient for an ordinary improvement
answer. The assistant may call `search_cards` afterward only when the question needs constraints
or alternatives beyond the returned swaps.

If deterministic analysis cannot propose a safe swap, the tool returns the diagnosis and an empty
swap list. The assistant explains the limitation instead of repeatedly searching.

## Error Handling and Limits

The tool uses the existing per-run tool budget and returns the established empty or bounded result
when that budget is exhausted. Database or analysis failures continue through the assistant's
existing recoverable-error path. No increase to token, request, tool-call, or timeout limits is
part of this change.

## Testing

Tests cover:

- the exact request "Can we improve my landbase?" selecting the new tool;
- a valid analysis containing grounded additions and removals;
- no proposed removal outside the current deck;
- an analysis with deficiencies but no available swaps;
- legacy assistant response conversion preserving returned mana recommendations;
- existing assistant, mana-base, lint, formatting, and type checks.

## Scope

This change does not redesign generic card search, alter the frontend API envelope, increase model
budgets, or add new user-configurable mana-base filters. Those constraints remain available through
an optional follow-up `search_cards` call.

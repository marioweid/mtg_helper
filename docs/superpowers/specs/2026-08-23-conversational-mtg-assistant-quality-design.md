# Conversational MTG Assistant Quality Design

**Date:** 2026-08-23
**Status:** Approved for implementation planning

## Summary

Improve the unified MTG Assistant so it gives confident, coherent deck-building advice while
remaining grounded in the user's deck, deterministic card data, and exact Oracle text. The target
experience is the strategic synthesis and conversational continuity of a strong general ChatGPT
answer, with stricter factual verification and direct use of the application's deck list, fit scores,
roles, themes, legality, bracket, and persistent preferences.

The change keeps one Pydantic AI agent and the existing deterministic tools. It does not introduce
fine-tuning, specialist-agent routing, conversation persistence, a second model provider, or a
second assistant pipeline.

## Problem

The current assistant has stronger underlying data than a general model but cannot consistently use
it in conversation:

- The frontend flattens recent user and assistant turns into one user-authored transcript.
- The model receives deck metadata and card count but not the complete deck manifest.
- Deck analysis exposes only a bounded weak-card shortlist, so arbitrary existing cards are not
  available for follow-up reasoning.
- The prompt emphasizes restrictions and tool mechanics more than coaching behavior.
- Normal chat output cannot retain structured, grounded card recommendations.
- Low response verbosity and a 2,048-token model setting constrain strategic explanations.
- Automatic memory commands can consume a deck-building question instead of answering it.
- Tests verify contracts and grounding but do not evaluate usefulness, continuity, prioritization,
  or invalid combo claims.

These constraints make the assistant feel less knowledgeable and less decisive than a general model
even when the application has better evidence.

## Product Behavior

The assistant is a confident but verified Commander deck-building partner. It should:

1. Infer the deck's intended plan from its commander, themes, contents, and preferences.
2. Answer the current question directly when the available context is sufficient.
3. Prefer a small, ranked package of high-conviction recommendations.
4. Explain how each recommendation interacts with the commander and existing deck.
5. Favor overlapping engines and modal cards over disconnected staples when evidence supports them.
6. Identify the first additions or changes the user should make.
7. Preserve the premise of prior turns, such as a Food-first rather than Squirrel-first Camellia deck.
8. Distinguish verified card facts from strategic judgment.
9. Ask one focused clarification question only when missing information would materially change the
   recommendation.

The assistant may use direct, opinionated language such as "best fit" or "add these first" when the
available evidence supports the ranking. It must reduce confidence or explain missing evidence
instead of presenting an unverified interaction as fact.

## Architecture

The unified `mtg_assistant` remains the sole owner of Commander Coach model behavior. A request uses
one bounded Pydantic AI run with role-aware recent history, a compact complete-deck manifest,
persistent Coach memory, and the existing deterministic tools plus one deck-card inspection tool.

```text
Current user turn + role-aware recent history
    -> unified MTG Assistant
        -> compact deck manifest and deck-level signals
        -> inspect exact existing deck cards when needed
        -> retrieve grounded additions
        -> analyze deck, mana, legality, and bracket
    -> natural reply + optional grounded action cards
```

No model-generated intermediate specialist reports or hidden routing model are added.

## Conversation Contract

`CommanderCoachRequest` gains a typed `history` list. Each history item contains:

- `role`: `user` or `assistant`;
- `content`: the visible natural-language message.

`message` contains only the latest user turn. The frontend sends recent completed turns separately
instead of embedding `User:` and `Assistant:` markers into `message`.

The backend converts history through the existing `to_model_messages()` boundary and supplies it to
`Agent.run(message_history=...)`. The server enforces bounded turn, per-message, and aggregate
character limits. It retains the most recent complete turns when truncation is necessary. Empty
messages are rejected and unknown roles cannot reach the model.

Chat history remains browser-session state. Refreshing the page may clear it. Database conversation
persistence and provider-side response storage remain outside scope, and `openai_store=False`
remains required.

The frontend and backend request contracts change together. No compatibility parser for flattened
transcripts is retained because the application controls both active callers and no persisted
flattened history exists.

## Deck Context

Every assistant run receives a compact deck briefing with:

- deck name, description, bracket, commander color identity, and selected themes;
- commander and partner names plus exact Oracle text;
- complete card manifest with name, quantity, mana value, type line, categories, tags, deck-fit
  score, deck-fit band, bounded fit reasons, and protection status;
- card count, role counts and targets, type counts, and mana curve;
- deck-level analysis signals that are already available without another model run; and
- persistent Coach memory.

The manifest does not include complete Oracle text for every card. This keeps routine input bounded
while allowing the model to see what the deck contains and how each card is classified.

An `inspect_deck_cards` tool accepts a bounded list of exact or case-insensitive card names from the
current deck. It returns the matching deck cards' exact Oracle text and the same role, fit, and
protection evidence used elsewhere. It cannot inspect arbitrary cards outside the deck. Unknown
names are reported explicitly.

The existing `search_cards` tool remains the source for new recommendations and returns exact Oracle
text and stable card identifiers. `analyze_deck` remains the source for deterministic structural
diagnosis and eligible weak-card evidence; it is not the only way the model can learn which cards
the deck contains.

## Prompt Design

The static prompt is reorganized in this order:

1. Product role and desired coaching behavior.
2. Turn workflow and answer-quality expectations.
3. Deck-specific reasoning and prioritization guidance.
4. Verification and grounding requirements.
5. Tool-selection details and product limitations.

The prompt instructs the model to inspect the deck before recommending additions, avoid generic
lists when deck-specific evidence exists, explain tradeoffs, and state an actionable priority order.
It must not ask for budget, bracket, combo tolerance, or deck identity when those facts are already
present in the deck briefing, memory, or conversation.

For a factual card interaction or combo claim, the model must inspect exact Oracle text for every
piece not already present in verified tool output. A claimed repeatable or infinite loop must account
for:

- the starting resources;
- each cost and trigger;
- the resources produced;
- how the sequence returns to the same or a better state; and
- the payoff that converts the loop into a game outcome, when relevant.

The model must not call a loop infinite when a required resource decreases on each iteration. It
must label strategic recommendations as recommendations rather than official rules conclusions.

## Response Contract

`chat`, `doctor`, and `replacement` remain distinct rendering modes:

- `chat` is the default for natural questions and follow-ups.
- `doctor` represents whole-deck findings, cuts, additions, and swaps.
- `replacement` represents focused advice for one existing card.

A chat answer may include grounded recommendations. The response envelope therefore gains a bounded
list of recommendation cards that can be rendered beneath the natural reply regardless of mode.
Each recommendation references a stable card identifier retrieved during the current run and
contains its reason, role match, and optional tradeoff. Ungrounded recommendations are removed before
serialization.

Doctor and replacement payloads retain their specialized structures. A chat answer does not gain
cuts or swaps merely because it contains recommendations. Existing cuts remain valid only when the
named card is in the current deck. Existing replacement target validation remains case-insensitive.

The frontend renders the natural reply first and grounded card recommendations beneath it. It shows
doctor UI only for whole-deck changes and replacement UI only for a focused replacement. The chat
reply remains useful if every structured recommendation is removed by grounding validation.

## Model Settings and Limits

The assistant retains the fixed OpenAI Responses model, one normal model run, bounded retries,
`openai_store=False`, the existing wall-clock timeout, and deterministic tool limits.

The initial quality settings are:

- maximum model output: 4,096 tokens;
- OpenAI text verbosity: medium for this workflow;
- reasoning effort: low until evaluation demonstrates that a higher supported setting produces a
  meaningful quality improvement;
- input token limit: unchanged unless the complete-deck briefing proves it cannot fit representative
  100-card decks and tool schemas.

The shared model-settings helper must permit workflow-specific text verbosity without changing the
other production agents. A model change or fine-tune requires separate evidence and design approval.

## Memory Behavior

Explicit memory-management commands such as "remember this", "forget this", and "show what you
remember" may remain deterministic.

Preference-bearing deck questions must not be intercepted as memory-only operations. For example,
"I prefer Food win conditions; what draw should I add?" must reach the assistant and receive a deck
answer. Persisting the preference automatically is optional only if it can occur without suppressing
the answer or adding another model run. Otherwise, the current answer takes priority and memory can
be edited through the existing UI or an explicit command.

## Grounding and Correctness

The following invariants remain enforced in code:

- Every recommended addition originates from `search_cards` or grounded mana-base analysis in the
  current run.
- Recommendation identity uses stable card identifiers, not model-produced name matching.
- Every cut exists in the current deck.
- Every replacement target exists in the current deck.
- Numeric fit scores and deterministic analysis values are passed through without model alteration.
- Legality and bracket conclusions come from their deterministic tools.
- Free-form reply text cannot create actionable UI cards by naming ungrounded additions.

The prompt and evaluation suite add a second layer for factual explanations. This does not claim to
provide a formal Magic rules engine. When exact card text is insufficient for a disputed rules
question, the assistant states that official rules lookup is not available rather than fabricating a
citation.

## Failure Handling

- Invalid history: reject the request with a clear validation error.
- Oversized history: retain the most recent complete turns within server limits.
- Deck briefing construction failure: log contextual failure and return the existing recoverable
  assistant response rather than silently running without deck context.
- Unknown inspected deck card: return the unmatched names to the model; do not perform global search.
- Tool timeout or budget exhaustion: answer from verified evidence already obtained and state the
  limitation when it affects the recommendation.
- Invalid model output: use the existing bounded retry and grounding filter.
- All structured recommendations removed: retain the natural chat reply without actionable cards.
- Model timeout or provider failure: retain the sanitized recoverable response and do not invoke a
  legacy assistant pipeline.

## Evaluation

A versioned evaluation corpus contains realistic deck fixtures and multi-turn conversations. Each
case defines:

- deck and memory fixture;
- conversation history and latest request;
- expected tool or evidence requirements;
- required response characteristics;
- forbidden factual claims or recommendations; and
- a scoring rubric.

The initial corpus covers:

1. Food-first Camellia win conditions.
2. A card-draw follow-up that preserves the Food-first premise.
3. Existing-card awareness that avoids recommending cards already present.
4. A named-card replacement.
5. Mana-base diagnosis.
6. A budget restriction from memory.
7. A no-infinite-combos preference from history or memory.
8. The invalid claim that Camellia and Ashnod's Altar alone form a repeatable Food loop.
9. An ambiguous theme that requires one clarification question.
10. An attempted ungrounded recommendation.

Responses are assessed on strategic usefulness, deck awareness, conversational continuity,
grounding, card-text correctness, prioritization, confidence calibration, and actionability. Exact
wording is not asserted.

Deterministic tests use Pydantic AI's test model for message-history wiring, tool contracts, prompt
payload shape, response grounding, and rendering modes. Model-backed quality evaluation is an
explicitly invoked test target because it incurs network cost and can vary. Its results must identify
the model and prompt version and preserve enough rubric output to compare iterations without logging
private production conversations.

## Testing

Backend tests verify:

- request history validation and truncation;
- role-aware messages reach `Agent.run` as model history;
- the latest request is not duplicated in history;
- complete deck manifests contain every deck card and bounded score evidence;
- `inspect_deck_cards` returns exact current-deck cards and reports unknown names;
- chat responses retain only grounded recommendation cards;
- doctor and replacement response behavior remains intact;
- preference-bearing questions are not consumed by memory handling;
- assistant-specific output and verbosity settings do not change other agents; and
- timeout, invalid output, and empty-grounding fallbacks remain sanitized.

Frontend tests verify:

- requests send separate latest-message and role-aware history fields;
- only completed visible turns enter history;
- history remains bounded without breaking user/assistant ordering;
- normal chat renders grounded recommendation cards;
- doctor and replacement rendering remains unchanged; and
- stream failure does not append an incomplete assistant turn.

The relevant Ruff, formatting, type-checking, frontend type-checking, and focused test commands must
pass without warnings before the change is considered complete.

## Migration Sequence

1. Add typed history and generic grounded recommendations to backend and frontend contracts.
2. Replace frontend transcript flattening with bounded structured history.
3. Build the compact deck briefing and `inspect_deck_cards` tool.
4. Pass role-aware message history to the unified Pydantic AI run.
5. Rewrite the assistant prompt around the approved coaching behavior and verification workflow.
6. Adjust assistant-specific output and text-verbosity settings.
7. Narrow memory interception to explicit memory-management requests.
8. Add deterministic contract, context, grounding, memory, and frontend tests.
9. Add the versioned model-backed evaluation corpus and establish baseline results.
10. Compare quality, factual correctness, latency, token use, and tool calls before considering any
    model or reasoning-effort change.

Old flattened-transcript handling is removed when structured history lands. The separate `/doctor`
endpoint and its agent are not consolidated as part of this work.

## Acceptance Criteria

- Follow-up turns preserve user and assistant roles instead of embedding a transcript in one user
  message.
- The model can identify every card already in the current deck before calling a tool.
- The model can retrieve exact Oracle text and fit evidence for any named current-deck card.
- A normal chat answer can return grounded recommendation cards without becoming a doctor response.
- The Camellia card-draw follow-up remains Food-focused and prioritizes deck-specific engines.
- The assistant does not claim that Camellia and Ashnod's Altar alone form the described infinite
  Food loop.
- Existing grounding, legality, bracket, cut, and replacement validation remains enforced.
- Preference-bearing questions receive an answer instead of only a memory confirmation.
- The fixed evaluation corpus records a measurable baseline and improved candidate result.
- Focused tests, lint, formatting, and type checks pass with no warnings.

## Out of Scope

- Fine-tuning or training on MTG conversations.
- A model router or multiple assistant personas.
- Restoring the removed specialist Coach pipeline.
- Persisting complete chat conversations in PostgreSQL.
- Provider-side conversation storage.
- A formal Magic Comprehensive Rules engine or official-rules retrieval tool.
- Changing deterministic deck-fit score formulas or card-search ranking.
- Redesigning the separate `/doctor` endpoint.

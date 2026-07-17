# Chat Empty State and Deck-Relative Card Scoring Design

**Date:** 2026-07-17
**Status:** Approved

## Summary

Improve the MTG Assistant chat empty state and give the Assistant deterministic evidence for weak
card selection. The chat starts without a prewritten user message or live draft bubble and instead
shows editable example-prompt cards. Deck cards receive a live, deck-relative fit score derived from
the existing Moxfield and Archidekt theme statistics plus bounded deck-context signals.

The score describes how well a card fits this deck. It is not a universal card-power rating.

## Chat Behavior

The chat prompt starts as an empty string. Editing the textarea does not create or update a chat
bubble. A user bubble is added only when the user sends a non-empty message.

Before the first message, the chat shows four example-action cards:

- Find the weakest cards in this deck.
- Suggest upgrades for my main theme.
- What should I replace this card with?
- Check my mana, draw, and interaction balance.

Selecting a card fills the textarea but does not submit it. The user can edit the text before
sending. The example cards remain visible while the conversation has no sent messages and disappear
after the first message is sent. Keyboard submission and the existing send button retain their
current behavior.

## Score Model

Scores are computed when deck detail is loaded rather than persisted. This avoids stale values when
the deck's selected themes or the Moxfield and Archidekt statistics change.

The scoring service returns, for every non-commander deck card:

- a normalized `deck_fit_score` from 0 to 100;
- a `deck_fit_band`: `strong`, `solid`, or `weak`; and
- a bounded list of `deck_fit_reasons` suitable for a tooltip and Assistant evidence.

The score combines:

1. the best stored synergy score across the deck's selected Moxfield hubs, Archidekt tags, or shared
   theme groups;
2. deterministic overlap with commander text and deck theme metadata;
3. whether the card fills a role currently below its target; and
4. a penalty for role redundancy or poor theme connection when the relevant role is already full.

Source scores must be normalized before combination so one provider cannot dominate because of a
different numeric range. The implementation plan will select fixed initial weights and band
thresholds using existing fixtures. Missing hub/tag data yields a lower-confidence score based on
local tags and roles; it must not be presented as equivalent source evidence.

Basic lands may be scored for completeness but are not normal replacement targets. Commanders and
partners are excluded from cut ranking.

## Assistant Cut Selection

`analyze_deck` exposes structured weak-card evidence instead of only card names. Each weak-card row
contains its score, band, concise reasons, and whether it is protected from ordinary cut advice.

The deterministic shortlist sorts eligible cards from weakest fit upward. It excludes or strongly
protects:

- the commander and partner;
- basic and ordinary lands unless the user asks for mana-base changes;
- pet or explicitly protected cards from account/deck preferences;
- known combo pieces;
- cards supporting a role that is currently below target; and
- cards the user explicitly says to preserve.

The language model explains and chooses among the shortlist, but it does not invent or modify the
numeric scores. If the user names a specific replacement target, the Assistant may analyze that card
even when it is protected, while warning about the relevant protection or role evidence.

## API and Data Flow

Deck detail enrichment remains read-time and deterministic:

1. Load the existing deck detail and selected archetype tags.
2. Resolve theme scores for all deck card IDs in one bounded database query.
3. Compute role budget and commander/deck overlap in application code.
4. Attach score fields to each `DeckCardItem`.
5. Reuse the same enriched cards in the Assistant's weak-card analysis.

No schema migration or score cache is required. Existing `DataResponse` envelopes remain unchanged.
The frontend TypeScript type mirrors the new optional score fields so older or partially enriched
responses degrade cleanly.

## Deck UI

The score is deliberately secondary. Card rows show a small muted colored dot or short fit label
near existing metadata. The exact numeric score and up to three reasons appear only in a title or
small tooltip. The score must not compete visually with card name, mana cost, quantity, ownership,
or combo/pet indicators.

The first implementation covers the compact deck list and the Assistant deck workspace. Other card
views can consume the same response fields later without introducing a second scoring system.

## Failure Handling

- No selected theme or no source statistics: use local role/tag evidence and mark reasons as local.
- Scoring query failure: return deck detail with score fields omitted and log the failure; deck
  viewing must remain available.
- No eligible weak cards: the Assistant reports that no high-confidence cut is available instead of
  recommending a protected card.
- Incomplete preference or combo information: omit that protection rather than claiming it exists.

## Testing

Frontend tests verify that:

- the textarea is initially empty;
- typing does not create a chat bubble;
- selecting an example card fills but does not send the prompt;
- example cards disappear after the first sent message; and
- fit metadata renders subtly when present and safely disappears when absent.

Backend tests verify that:

- higher source synergy and commander/theme overlap increase deck fit;
- underfilled-role support protects a card from weak ranking;
- weak cards are sorted deterministically;
- commanders, partners, lands, pet/protected cards, and combo pieces are excluded as specified;
- missing source statistics use labeled local evidence; and
- a scoring failure does not prevent deck detail from loading.

Assistant tests verify that replacement requests call deck analysis and ground proposed cuts in the
returned weak-card evidence.

## Acceptance Criteria

- Opening the Assistant shows an empty textarea and no fake user bubble.
- Draft edits never appear in conversation history before sending.
- Four action cards populate editable prompts without automatically sending them.
- Every scored card uses one deterministic, shared deck-relative scoring implementation.
- Replacement requests prefer low-fit eligible cards and explain their deck-specific weakness.
- Protected cards are not ordinary cut suggestions.
- The deck UI exposes score context without making it a primary visual element.
- No database migration or persisted score invalidation is introduced.

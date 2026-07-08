# Commander Suggestor Design

## Context

MTG Helper currently supports three deck-start paths:

- Pick a commander and manually choose archetype keywords.
- Pick a commander and chat with the agent to extract keywords.
- Import a deck list or URL, then refine detected keywords.

All of these require the commander to be known before the strategy intake. The new
Commander Suggestor adds a fourth path for players who know the play pattern they want
but not the commander. Example prompts include "I want graveyard synergies" or "I want
lots of ETB value."

The feature uses only the local card database. The app already syncs Scryfall data
periodically, so local data remains the source of truth for legality, oracle text,
keywords, tags, traits, and card metadata.

## Goals

- Let a user describe a desired Commander deck before choosing a commander.
- Show a live ranked top 8 commander board that updates after each chat turn.
- Recommend only cards that are legal and valid as commanders.
- Strongly prioritize commanders with card advantage or repeatable value in the command
  zone.
- Carry the final inferred strategy directly into deck creation and route to the build
  wizard.
- Use both curated archetype tags and printed mechanics when matching intent.

## Non-Goals

- No live Scryfall or EDHREC lookup during commander suggestion.
- No vector search requirement for the first version.
- No deck list generation in this flow. The existing build wizard remains responsible for
  filling the deck.
- No user-visible "AI picked this commander" result without deterministic backend
  validation and ranking.

## User Flow

Add a new option on `/decks/new`: **Suggest a commander**.

The new `/decks/new/suggest` page has two main regions:

- Chat/intake: the user describes the desired play pattern and answers short follow-up
  questions.
- Live commander board: the current top 8 commanders, updated after every turn and after
  local filter changes.

Example flow:

1. User says: "I want graveyard synergies."
2. Backend infers tags such as `graveyard`, possible branches such as `reanimator`,
   `sacrifice`, `aristocrats`, and traits such as `etb`.
3. The top 8 board immediately shows graveyard-friendly commanders.
4. Assistant asks one focused question, such as: "Do you want ETB value loops, sacrifice
   loops, or big reanimation targets?"
5. User answers. The intent and top 8 update.
6. User optionally tweaks chips or color identity filters.
7. User picks a commander.
8. The frontend calls the existing deck creation endpoint with the selected commander,
   inferred `archetype_tags`, `stage_targets`, bracket, and description.
9. The app routes to `/decks/{id}/build`.

The default result count is 8 commanders.

## API Design

Add `POST /api/v1/decks/suggest-commanders`.

Register this static route before dynamic `/{deck_id}` routes so FastAPI never treats
`suggest-commanders` as a deck ID.

Request model:

- `history: list[DescribeMessage]`
- `message: str`
- `intent_override: CommanderSuggestIntent | None`
- `limit: int = 8`

`intent_override` lets the frontend re-run ranking after the user toggles chips, colors,
or bracket without forcing the LLM to reinterpret the whole conversation.

Response model:

- `reply: str`
- `done: bool`
- `intent: CommanderSuggestIntent`
- `commanders: list[CommanderSuggestion]`
- `stage_targets: dict[str, int] | None`
- `suggested_name: str | None`

`CommanderSuggestIntent`:

- `archetype_tags: list[str]`
- `mechanic_tags: list[str]`
- `traits: list[str]`
- `token_types: list[str]`
- `color_identity: list[str] | None`
- `excluded_colors: list[str]`
- `bracket: int`
- `direction: str`
- `must_have: list[str]`
- `avoid: list[str]`

`CommanderSuggestion`:

- `card: CardResponse`
- `score: float`
- `score_reasons: list[str]`
- `matched_tags: list[str]`
- `matched_traits: list[str]`
- `matched_token_types: list[str]`
- `card_advantage_reasons: list[str]`

All responses use the existing `DataResponse[T]` envelope.

## Backend Architecture

Add a new service module, `commander_suggestor_service.py`, with three responsibilities:

1. Interpret the conversation into structured intent.
2. Query valid local commander candidates.
3. Rank candidates deterministically.

The LLM is only allowed to return structured intent and one follow-up question. It does
not return commander names. This keeps legality and ranking grounded in local data.

Candidate query uses `cards` and filters:

- `legalities->>'commander' = 'legal'`
- Valid commander card:
  - `type_line ILIKE '%Legendary%' AND type_line ILIKE '%Creature%'`
  - Include local-data-supported exceptions when oracle text explicitly says the card can
    be your commander.
- Exclude gold border, acorn, conspiracies, and other non-playable records using the same
  safety filters used by card resolution.

The first version does not need a new table.

## Ranking Model

Each candidate receives a weighted score from local fields:

- Theme overlap: `cards.tags && intent.archetype_tags`
- Mechanic overlap: `cards.tags && intent.mechanic_tags`
- Trait overlap: `cards.traits && intent.traits`
- Token overlap: `cards.token_types && intent.token_types`
- Color fit: candidate color identity equals or is a subset of requested colors, and does
  not include excluded colors.
- Popularity tie-break: lower `edhrec_rank` is better.
- Bracket fit: cheap, efficient, deterministic engines score better for higher brackets;
  slower battlecruiser text is acceptable at lower brackets.
- Command-zone card advantage boost.

Card advantage in the command zone is a first-class ranking signal. The scorer should
boost commanders whose oracle text indicates repeatable card or material advantage:

- Direct card draw.
- Card selection, surveil, investigate, discover, impulse draw, or play-from-exile.
- Recursion from graveyard, especially repeatable recursion.
- Token production that creates ongoing material advantage.
- Cast/copy/play extra cards or spells from non-hand zones.
- ETB, death, sacrifice, or spell-cast triggers that convert normal gameplay into cards or
  resources.

The response explains major score reasons in plain terms, such as "Graveyard engine",
"ETB payoff", "Card advantage in command zone", or "Matches Sultai colors."

## Follow-Up Questions

The agent asks one short question per turn while still returning live commander results.
Questions should narrow the highest-impact ambiguity:

- For graveyard: ETB value, sacrifice loops, self-mill, or big reanimation targets.
- For ETB: blink, clone/copy, token copies, or creature toolbox value.
- For colors: preferred colors or colors to avoid.
- For power: casual value, upgraded synergy, optimized, or cEDH-leaning.

The agent should stop asking when the top results and intent are stable enough, but users
can keep refining manually.

## Keyword Strategy

Keep two distinct vocabularies:

- Curated archetype tags are deck-building concepts, such as `graveyard`, `reanimator`,
  `blink`, `aristocrats`, `landfall`, and `spellslinger`.
- Full mechanics are printed mechanics or ability words, such as `dredge`, `escape`,
  `descend`, `forage`, `plot`, and `saddle`.

The keyword editor should expose both layers, as it does today, but the backend and
frontend lists must stay synchronized. Add a regression test that compares:

- `extract_agent.KEYWORD_VOCAB`
- `tag_service` curated tag outputs
- `frontend/lib/constants.ts` archetype tags
- `frontend/lib/mechanics.ts` mechanic tags

When new local keyword metadata appears from Scryfall or MTGJSON sync, add useful brewing
tags to the curated layer only if they help users describe deck plans. Printed mechanics
can live in the full mechanics layer without becoming archetypes.

## Frontend Design

Add `/decks/new/suggest`.

Core UI:

- Compact chat column with the current assistant question and answer input.
- Live top 8 commander grid with image, name, color identity, short reason chips, and
  score details.
- Editable inferred chips for archetypes and mechanics.
- Color identity selector.
- Bracket selector using existing bracket labels.
- Primary action on each commander: **Create deck & start building**.

The page should follow existing deck-start patterns, but it should feel more like a
brewing workbench than a static form. The commander board must remain visible and update
after every turn.

## Error Handling

- If the LLM fails, keep the last valid intent and allow manual chip/color edits to rerun
  deterministic ranking.
- If no candidates match strict color filters, return an empty list plus a reply suggesting
  the user loosen colors or tags.
- If a selected commander no longer exists or fails validation at deck creation time,
  return the existing card/deck creation error.
- Rate limit this endpoint like the existing keyword extraction endpoint.

## Testing

Backend tests:

- Request/response model validation.
- Candidate query excludes non-commanders and Commander-illegal cards.
- "Can be your commander" oracle text exceptions are included.
- Card advantage scoring boosts draw/card-selection/value commanders.
- Graveyard + ETB intent ranks overlapping commanders above generic graveyard cards.
- Color identity include/exclude filters are enforced.
- Empty result behavior is stable.

Frontend tests or focused component checks:

- New deck option links to `/decks/new/suggest`.
- Chat turn updates intent chips and commander results.
- Manual chip/color edits rerun ranking through `intent_override`.
- Selecting a commander creates a deck and routes to `/decks/{id}/build`.

Regression tests:

- Backend/frontend keyword vocabularies do not drift.

## Open Implementation Notes

- Use the existing `KeywordExtractResponse` pattern as a model for the new structured
  agent response, but keep the suggestor models separate because they include colors,
  traits, token types, and commander candidates.
- Reuse existing `CardResponse` in `CommanderSuggestion` to avoid a duplicate card shape.
- Consider adding cached generated score reasons later if ranking becomes expensive, but
  start stateless and SQL-driven.

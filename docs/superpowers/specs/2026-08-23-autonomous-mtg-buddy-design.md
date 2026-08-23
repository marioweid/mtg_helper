# Autonomous MTG Buddy Design

## Goal

Turn the existing Commander assistant into a proactive, conversational MTG brewing partner that
answers directly and uses deterministic tools as supporting evidence rather than as a mandatory
dialogue workflow.

## Problem

The current assistant requires theme lookup before thematic card discovery and tells the model to
clarify whenever that lookup is empty or ambiguous. This creates permission loops even when the
user's intent is clear. Internal fallback and tool limitations leak into replies, making the
assistant feel like a search interface instead of an MTG buddy.

The underlying data is already connected correctly. Enabled administrator theme groups resolve to
their Moxfield hub and Archidekt tag members, and their card statistics feed card search ranking.
The redesign must preserve that evidence while making it optional and invisible to normal
conversation.

## Principles

- Keep one Pydantic AI agent. No router model, specialist agents, or fine-tuning.
- Let the model answer strategic and conversational questions without tools.
- Require database grounding for actionable card additions.
- Treat theme groups and source hubs as ranking evidence, not hard filters.
- Ask only when missing information materially changes legality, budget, or strategy.
- Make reasonable, reversible assumptions and state them briefly.
- Never narrate tools, pipelines, IDs, scores, or internal fallback behavior.
- Keep execution bounded by tool, request, token, and wall-clock limits.
- Add no new runtime dependency.

## Agent Harness

The stable system prompt defines identity, conversational behavior, grounding boundaries, and stop
conditions. It does not prescribe a fixed sequence of tool calls.

The assistant behaves like an experienced Commander brewing partner:

- answer first and have an informed opinion;
- acknowledge the deck's identity without generic praise;
- prefer three to five deck-specific recommendations;
- explain why each card works with the commander or existing package;
- mention a tradeoff only when it changes the decision;
- respect bracket, budget, and protected cards;
- avoid repeated openings, restating the request, and generic closing offers.

Runtime dependencies carry the deck, grounded recommendations, and tool budget. Dynamic context is
provided in the request payload: complete compact deck briefing, saved preferences, and structured
conversation references. The model retains automatic tool choice.

## Unified Card Discovery

The model sees one `find_cards` tool rather than a required `search_themes` then `search_cards`
sequence. Its typed request contains:

- a natural-language `query` describing the desired role or interaction;
- optional theme hints;
- structural card filters;
- budget and result count;
- whether existing deck cards should be excluded;
- a ranking mode.

The service resolves each theme hint against enabled administrator groups, Moxfield hubs, and
Archidekt tags. It also considers the deck's canonical archetype tags when they are relevant. Theme
statistics boost matching cards. If no theme resolves, source statistics are unavailable, or the
theme pool has no structural matches, the same request runs against the legal global card database.
This fallback is silent to the conversation.

Search results retain internal provenance:

- resolved theme tags;
- theme score;
- matched structural filters;
- commander text overlap;
- detected functional roles;
- game-changer status;
- whether global fallback was used.

The assistant uses that evidence to make a judgment but does not expose retrieval terminology.

## Grounding

Strategic advice, archetype discussion, and analysis of the current deck can be answered directly.
Every actionable addition in structured output must reference a card returned by `find_cards` in the
current run. Recent references help resolve follow-ups, but the agent searches again before returning
them as actionable cards.

Current-deck interactions may use the deck briefing. Exact Oracle-text claims about a main-deck card
use `inspect_deck_cards`. The commander and partner Oracle text are already present in the briefing.

Response conversion drops unknown recommendations and cuts as it does today. It also preserves
grounded prior recommendations so follow-up requests can refer to them without searching again.

## Conversation State

Assistant history turns gain optional grounded recommendation references containing Scryfall ID and
card name. The frontend records references from each completed response and sends them with future
history. This helps resolve requests such as "the second one", "which of those is best", and "keep
Skullclamp" without relying only on prior prose. References are not trusted as current grounding.

History remains client-owned and bounded. No conversation table or migration is introduced.

## Progress Experience

Detailed backend events remain available for telemetry. The normal coach UI displays one current,
replaceable status rather than an accumulated internal timeline. Raw event names, memory routing,
tool selection, grounding, completion events, and tool-call counts are not shown.

## Failure Behavior

- Empty or ambiguous theme lookup: continue with the most relevant resolved themes or global search.
- No card matches: give useful strategic guidance and say no verified additions matched the stated
  constraints.
- Discovery unavailable: do not invent additions; answer strategy from deck context.
- Tool budget exhausted: synthesize from evidence already collected.
- Genuine decision-blocking ambiguity: ask one concise question.
- Database unavailable: preserve non-recommendation conversation and fail actionable additions
  honestly.

## Evaluation

Deterministic tests cover theme resolution, silent fallback, grounding, prior recommendation reuse,
prompt policy, history bounds, and progress reduction. Database tests prove that administrator groups
containing Moxfield and Archidekt members affect retrieval.

The versioned quality corpus records expected behavior for direct answers, recommendation turns,
fallback, ambiguity, follow-up references, bracket guidance, and unsupported cards. The evaluator
validates observable requirements and supports scoring captured assistant runs without coupling tests
to hidden reasoning.

## Scope

Expected implementation areas:

- `backend/src/mtg_helper/models/ai.py`
- `backend/src/mtg_helper/services/mtg_assistant.py`
- `backend/src/mtg_helper/services/mtg_card_search.py`
- backend assistant, search, theme, and evaluation tests
- `frontend/lib/coach-conversation.ts`
- `frontend/app/decks/[id]/coach/page.tsx`
- frontend conversation and progress tests

No new agent, database table, API endpoint, or runtime package is required.

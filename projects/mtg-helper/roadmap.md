# Development Roadmap

## Completed Phases

### Phase 1 — Foundation (Done)

- [x] Project scaffolding (FastAPI + Docker Compose + PostgreSQL)
- [x] Scryfall bulk data pipeline
- [x] Database schema
- [x] Card search API
- [x] Color identity and legality filtering
- [x] Basic deck CRUD endpoints

### Phase 2 — AI Deck Building (Done)

- [x] OpenAI GPT integration
- [x] Prompt engineering for staged deck building
- [x] Deck creation flow (commander + strategy → staged card generation)
- [x] Card validation (AI suggestions verified against local DB)
- [x] Card suggestion endpoint
- [x] Conversation history (per-deck context)
- [x] Moxfield export format

### Phase 3 — Preferences and Feedback (Done)

- [x] Thumbs up/down on card suggestions
- [x] Account-level preferences (pet cards, avoid list, avoid archetypes)
- [x] Preference injection into AI prompts
- [x] Bracket-aware prompt tuning

### Phase 4 — Frontend (Done)

- [x] Next.js project setup
- [x] Deck builder page (commander selection, strategy input)
- [x] Staged building UI (review cards per stage, accept/reject)
- [x] Card suggestion panel (search, ranked results with images)
- [x] Deck view (card list with images, categories, curve chart)
- [x] Preference management page
- [x] Moxfield export button

### Phase 5 — Polish (Done)

- [x] Deck statistics (mana curve, color distribution, category breakdown)
- [x] Recommended ratios (target counts per category)
- [x] Scryfall data auto-refresh (weekly cron sidecar + startup sync)
- [x] Error handling and loading states (error.tsx / loading.tsx boundaries)
- [x] Mobile-friendly layout (viewport meta, responsive nav, chat height)

---

## Phase 6 — Build Wizard Redesign

Overhaul the deck building experience: free stage navigation, better card interaction, and smarter AI prompting.

### 6.1 — Stage Reorder and Rename

Change the build stage sequence and rename "Removal" to "Interaction".

**New order:** Ramp → Interaction → Draw → Theme → Utility → Lands

- [ ] Backend: update `STAGES` list in `deck_service.py` to new order
- [ ] Backend: rename `"removal"` → `"interaction"` in `STAGES`
- [ ] Backend: update `_STAGE_META` in `ai_service.py` — rename key, update label to `"interaction / removal and protection"`
- [ ] Backend: update interaction stage prompt to include counterspells, board wipes, hexproof/shroud givers (Lightning Greaves, Swiftfoot Boots), indestructible effects (Heroic Intervention, Totem Armor)
- [ ] Frontend: update `STAGES` and `STAGE_LABELS` in `constants.ts`
- [ ] Frontend: rename `CATEGORY_TARGETS` key `removal` → `interaction`
- [ ] Frontend: update `CATEGORY_ORDER` in `deck-stats.tsx` and `page.tsx` (deck detail)
- [ ] Migrate any existing deck data: update `deck_cards.category` rows with `'removal'` → `'interaction'`

### 6.2 — Flexible Stage Navigation

Replace the linear "next stage" wizard with free tab-based navigation across all stages.

- [ ] Backend: add optional `stage` parameter to `POST /decks/{id}/build` — when provided, generate suggestions for that specific stage instead of auto-advancing
- [ ] Backend: add Pydantic request body `BuildRequest(stage: str | None, target: int | None)` in `routers/ai.py`
- [ ] Backend: update `ai_service.build_stage()` to accept and use the `stage` parameter
- [ ] Frontend: update `apiClient.buildStage()` in `api.ts` to accept optional `{ stage, target }` body
- [ ] Frontend: build page — render a tab bar showing all 6 stages (Ramp, Interaction, Draw, Theme, Utility, Lands), all clickable from the start
- [ ] Frontend: clicking a tab switches the active stage; if not yet loaded, auto-fetch suggestions
- [ ] Frontend: store per-stage state (suggestions, statuses, target, loaded flag) so navigating back shows cached results without re-fetching
- [ ] Frontend: show a checkmark on stage tabs where accepted count ≥ target
- [ ] Frontend: remove the old sequential "Next Stage" / "Review remaining" button

### 6.3 — Per-Stage Target Count

Let the user choose how many cards of each type they want before the AI suggests.

- [ ] Frontend: add `STAGE_DEFAULTS` to `constants.ts` with sensible defaults (ramp: 10, interaction: 9, draw: 9, theme: 22, utility: 6, lands: 36)
- [ ] Frontend: at the top of each stage, show a target stepper: `[−]` number input `[+]` — pre-filled with the default, editable (type a number or use buttons)
- [ ] Frontend: show accepted count vs target as `X / Y` next to the stepper
- [ ] Frontend: changing the target updates the display only — does not re-fetch cards
- [ ] Backend: when `target` is provided in the build request, use it in the AI prompt instead of the default range from `_STAGE_META` (e.g., "suggest 12 ramp cards" instead of "suggest 10-12")

### 6.4 — Reversible Accept / Reject

Cards stay visible after the user acts on them. Both accept and reject are reversible.

- [ ] Frontend: accepted cards stay in the grid with a green indicator (✓ Added) and a small remove (×) button
- [ ] Frontend: clicking remove on an accepted card calls `apiClient.removeCard()`, sets status back to pending or rejected
- [ ] Frontend: rejected cards stay in the grid, faded/dimmed, with an "Add" button
- [ ] Frontend: clicking "Add" on a rejected card calls `apiClient.addCard()`, sets status to accepted
- [ ] Frontend: update `CardSuggestionCard` component with new props: `onUndo`, `onRemove`
- [ ] Frontend: accepted status shows green border + "✓ Added" label + remove button (replaces old "Added to deck" footer)
- [ ] Frontend: rejected status shows faded card + "Add" button (replaces old "Rejected" footer)

### 6.5 — Load More Suggestions

Add a "Load More" button to fetch additional AI suggestions for the current stage without losing existing cards.

- [ ] Frontend: show a "Load More" button below the card grid (visible once the stage has been loaded at least once)
- [ ] Frontend: clicking "Load More" calls `buildStage({ stage, target })` for the current stage
- [ ] Frontend: append new suggestions to the existing list, deduplicating by `scryfall_id`
- [ ] Frontend: new cards start as `"pending"`; existing card statuses are preserved
- [ ] Backend: ensure the AI prompt includes the list of already-suggested card names (from the request or from the deck's current cards) so it avoids repeating them

### 6.6 — Basic Land Quantity Stepper

Allow adding multiple copies of basic lands (Forest, Mountain, etc.) via a quantity control instead of single-add.

- [ ] Frontend: detect basic lands by checking if `type_line` includes `"Basic Land"`
- [ ] Frontend: for basic land suggestion cards, show a quantity stepper: `[−]` editable number `[+]`, min 1, max 99, default 1
- [ ] Frontend: when accepting a basic land, pass the selected quantity to `apiClient.addCard()` (the `quantity` field already exists in `DeckCardAdd`)
- [ ] Frontend: add `isBasicLand`, `quantity`, and `onQuantityChange` props to `CardSuggestionCard`
- [ ] Frontend: the accepted count for the Lands stage increments by the quantity, not just by 1

---

## Future (Not Planned)

- Multi-user authentication
- GCP deployment
- CLI client
- Qdrant vector search for card similarity
- Price-aware suggestions
- Collection integration
- Double-check bracket definitions

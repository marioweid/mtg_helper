# Development Roadmap

## Phase 1 — Foundation

Get the data pipeline and core backend working. No frontend yet.

- [ ] Project scaffolding (FastAPI + Docker Compose + PostgreSQL)
- [ ] Scryfall bulk data pipeline (download, parse, upsert into cards table)
- [ ] Database schema (cards, decks, deck_cards, preferences, feedback, conversations)
- [ ] Card search API (by name, color identity, type, text, CMC)
- [ ] Color identity and legality filtering
- [ ] Basic deck CRUD endpoints

## Phase 2 — AI Deck Building

The core experience: AI-powered deck creation and suggestions.

- [ ] Claude API integration (service abstraction)
- [ ] Prompt engineering for staged deck building
- [ ] Deck creation flow (set commander + strategy → staged card generation)
- [ ] Card validation (every AI suggestion verified against local DB)
- [ ] Card suggestion endpoint (partial deck + constraints → ranked suggestions)
- [ ] Conversation history (per-deck context continuity)
- [ ] Moxfield export format

## Phase 3 — Preferences and Feedback

Make the AI learn and adapt.

- [ ] Thumbs up/down on card suggestions (deck-level)
- [ ] Account-level preferences (pet cards, avoid list, avoid archetypes)
- [ ] Preference injection into AI prompts
- [ ] Bracket-aware prompt tuning (casual vs strong)

## Phase 4 — Frontend

Build the web UI.

- [ ] Next.js project setup
- [ ] Deck builder page (commander selection, strategy input)
- [ ] Staged building UI (review cards per stage, accept/reject)
- [ ] Card suggestion panel (search, ranked results with images)
- [ ] Deck view (card list with images, categories, curve chart)
- [ ] Preference management page (pet cards, avoid list)
- [ ] Moxfield export button

## Phase 5 — Polish

Refinement and quality of life.

- [ ] Deck statistics (mana curve, color distribution, category breakdown)
- [ ] Recommended ratios (draw spells vs lands, ramp count, etc.)
- [ ] Scryfall data auto-refresh (weekly cron)
- [ ] Error handling and loading states
- [ ] Mobile-friendly layout

## Future (Not Planned)

- Multi-user authentication
- GCP deployment
- CLI client
- Qdrant vector search for card similarity
- Price-aware suggestions
- Collection integration

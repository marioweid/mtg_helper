# Core Workflows

## 1. Deck Creation (Staged Building)

```
User: "Build me a Hazel of the Rootbloom deck focused on token copies
       and big X spells as finishers. Bracket 3."
                        │
                        ▼
              ┌─────────────────┐
              │ Validate commander│
              │ (Scryfall local) │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ AI analyzes      │
              │ commander +      │
              │ strategy + bracket│
              └────────┬────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Stage 1: Core Theme (20-25)  │◀── User reviews, thumbs up/down
        │ Token copy synergies, X spells│
        ├──────────────────────────────┤
        │ Stage 2: Ramp (10-12)        │◀── User reviews, thumbs up/down
        │ Mana acceleration            │
        ├──────────────────────────────┤
        │ Stage 3: Draw/Card Advantage │◀── User reviews, thumbs up/down
        │ (8-10 cards)                 │
        ├──────────────────────────────┤
        │ Stage 4: Removal/Interaction │◀── User reviews, thumbs up/down
        │ (8-10 cards)                 │
        ├──────────────────────────────┤
        │ Stage 5: Utility/Flex (5-8)  │◀── User reviews, thumbs up/down
        │ Protection, recursion, etc.  │
        ├──────────────────────────────┤
        │ Stage 6: Mana Base (35-38)   │◀── User reviews
        │ Lands                        │
        └──────────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Deck complete    │
              │ Save + export    │
              └─────────────────┘
```

At each stage, the AI provides:
- A recommended number of cards for that category
- A ranked list of suggestions with explanations
- Synergy callouts (e.g., "works with Doubling Season already in your list")
- Curve considerations

The user can accept, reject, swap, or ask for alternatives at each stage.

## 2. Card Suggestion (Interactive Refinement)

```
User has 80 cards in a deck, wants to fill remaining slots.

User: "I need 2-color cards that care about +1/+1 counters"
                        │
                        ▼
              ┌─────────────────────┐
              │ Build AI context:    │
              │ - Current deck list  │
              │ - Commander identity │
              │ - Deck-level feedback│
              │ - Account preferences│
              │ - Conversation history│
              │ - Bracket target     │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │ AI suggests 10-15   │
              │ cards, ranked, with:│
              │ - Card image        │
              │ - Why it fits       │
              │ - Synergy callouts  │
              │ - Curve impact      │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │ User reviews:       │
              │ 👍 Add to deck      │
              │ 👎 Reject (stored)  │
              │ Ask for more        │
              └─────────────────────┘
```

## 3. Preference Management

### Per-Deck Preferences (via feedback)

- Thumbs up/down on individual card suggestions
- Natural language constraints ("no counterspells in this deck")
- Stored in `deck_feedback` and conversation history
- Only affect the current deck

### Account-Level Preferences

- **Pet cards** — Cards to proactively include when on-color and relevant
  - e.g., "Monologue Tax" — always consider in white decks
- **Avoid cards** — Cards to never suggest
  - e.g., "Rhystic Study" — never suggest this card
- **Avoid archetypes** — Strategies to avoid
  - e.g., "No stax", "No mass land destruction"
- **General preferences** — Broader taste signals
  - e.g., "I prefer creatures over enchantments"

Both tiers are injected into every AI prompt as system context.

## 4. Moxfield Export

Generate a Moxfield-compatible deck list for import:

```
1 Hazel of the Rootbloom *CMDR*
1 Doubling Season
1 Parallel Lives
1 Green Sun's Zenith
...
```

Supports Moxfield's category tags and commander designation.

## 5. Scryfall Data Pipeline

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────┐
│ Scryfall Bulk    │     │ Download +       │     │ PostgreSQL   │
│ Data Endpoint    │────▶│ Parse JSON       │────▶│ Upsert cards │
│ (daily update)   │     │ (~80k cards)     │     │              │
└──────────────────┘     └─────────────────┘     └──────────────┘
```

- **Initial load:** Download full bulk data, parse, insert into `cards` table
- **Refresh:** Weekly (or on-demand) — download, diff, upsert changed cards
- **Filtering:** Only import Commander-legal cards to reduce noise
- **Runtime:** Triggered via CLI command or API endpoint

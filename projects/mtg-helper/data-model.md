# Data Model

## Entity Relationship

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│   accounts   │──1:N──│      decks       │──1:N──│  deck_cards  │
└──────┬───────┘       └──────┬───────────┘       └──────┬───────┘
       │                      │                          │
       │ 1:N                  │ 1:N                      │ N:1
       │                      │                          │
┌──────▼───────┐  ┌───────────▼──────────┐       ┌──────▼───────┐
│  preferences │  │  conversation_turns  │       │    cards     │
└──────────────┘  └──────────────────────┘       └──────────────┘
```

## Tables

### cards

Populated from Scryfall bulk data. Source of truth for all card information.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| scryfall_id | UUID | Scryfall's unique ID |
| oracle_id | UUID | Groups printings of the same card |
| name | TEXT | Card name |
| mana_cost | TEXT | Mana cost string (e.g., `{2}{G}{G}`) |
| cmc | DECIMAL | Converted mana cost |
| type_line | TEXT | Full type line |
| oracle_text | TEXT | Rules text |
| color_identity | TEXT[] | Color identity array (`['G', 'W']`) |
| colors | TEXT[] | Card colors |
| keywords | TEXT[] | Keyword abilities |
| power | TEXT | Power (nullable) |
| toughness | TEXT | Toughness (nullable) |
| legalities | JSONB | Legality per format |
| image_uri | TEXT | Scryfall image URL (normal size) |
| prices | JSONB | Current prices |
| rarity | TEXT | common/uncommon/rare/mythic |
| set_code | TEXT | Set code |
| released_at | DATE | Release date |
| edhrec_rank | INTEGER | EDHREC popularity rank (nullable) |
| updated_at | TIMESTAMPTZ | Last sync time |

**Indexes:** name (GIN trigram for fuzzy search), color_identity (GIN), oracle_text (GIN full-text), legalities, cmc, type_line

### accounts

Minimal for now — single user, multi-user ready.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| display_name | TEXT | User's display name |
| created_at | TIMESTAMPTZ | Account creation time |

### decks

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| owner_id | UUID | FK to accounts (nullable for now) |
| name | TEXT | Deck name |
| commander_id | UUID | FK to cards |
| partner_id | UUID | FK to cards (nullable, for partner commanders) |
| description | TEXT | Strategy/tone description from user |
| bracket | INTEGER | Target power level (1-4) |
| stage | TEXT | Building stage (e.g., `ramp`, `removal`, `theme`, `lands`, `complete`) |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last modification |

### deck_cards

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| deck_id | UUID | FK to decks |
| card_id | UUID | FK to cards |
| quantity | INTEGER | Count (usually 1 in Commander) |
| category | TEXT | Deck category (ramp, draw, removal, theme, wincon, lands, etc.) |
| added_by | TEXT | `user` or `ai` |
| ai_reasoning | TEXT | Why the AI suggested this card (nullable) |

### preferences

Account-level preferences that persist across all decks.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| account_id | UUID | FK to accounts |
| preference_type | TEXT | `pet_card`, `avoid_card`, `avoid_archetype`, `general` |
| card_id | UUID | FK to cards (nullable, for card-specific prefs) |
| description | TEXT | Free text (e.g., "I hate stax") |
| created_at | TIMESTAMPTZ | Creation time |

### deck_feedback

Per-deck card feedback (thumbs up/down on suggestions).

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| deck_id | UUID | FK to decks |
| card_id | UUID | FK to cards |
| feedback | TEXT | `up` or `down` |
| reason | TEXT | Optional reason (nullable) |
| created_at | TIMESTAMPTZ | Feedback time |

### conversation_turns

Stores AI conversation history per deck for context continuity.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| deck_id | UUID | FK to decks |
| role | TEXT | `user` or `assistant` |
| content | TEXT | Message content |
| turn_order | INTEGER | Sequence number |
| created_at | TIMESTAMPTZ | Message time |

## Views

### deck_detail_view

Joins deck_cards with cards to provide a human-readable deck list with full card info, images, and categories. Used by the frontend for deck display.

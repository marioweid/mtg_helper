# API Design

## Base URL

`http://localhost:8000/api/v1`

## Endpoints

### Cards

| Method | Path | Description |
|--------|------|-------------|
| GET | `/cards/search` | Search cards with filters |
| GET | `/cards/{scryfall_id}` | Get card by Scryfall ID |
| POST | `/cards/sync` | Trigger Scryfall bulk data refresh |

**GET /cards/search** query params:
- `q` — text search (name + oracle text)
- `color_identity` — exact or subset match (e.g., `GW`)
- `type` — type line contains (e.g., `creature`, `enchantment`)
- `cmc_min` / `cmc_max` — mana value range
- `keywords` — keyword abilities (e.g., `flying,trample`)
- `commander_legal` — boolean, default true
- `limit` / `offset` — pagination

### Decks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/decks` | List all decks |
| POST | `/decks` | Create a new deck |
| GET | `/decks/{id}` | Get deck with full card details |
| PATCH | `/decks/{id}` | Update deck metadata |
| DELETE | `/decks/{id}` | Delete a deck |
| POST | `/decks/{id}/cards` | Add cards to deck |
| DELETE | `/decks/{id}/cards/{card_id}` | Remove card from deck |
| GET | `/decks/{id}/export/moxfield` | Export deck in Moxfield format |

**POST /decks** request body:
```json
{
  "commander_scryfall_id": "uuid",
  "partner_scryfall_id": "uuid | null",
  "name": "Hazel Token Copies",
  "description": "Token copies and big X spells as finishers",
  "bracket": 3
}
```

### AI / Deck Building

| Method | Path | Description |
|--------|------|-------------|
| POST | `/decks/{id}/build` | Start or continue staged deck building |
| POST | `/decks/{id}/suggest` | Get card suggestions for a deck |
| POST | `/decks/{id}/chat` | Free-form chat about the deck |

**POST /decks/{id}/build** request body:
```json
{
  "action": "next_stage"
}
```

Response includes the current stage, suggested cards (with images, reasoning, synergies), and recommended counts.

**POST /decks/{id}/suggest** request body:
```json
{
  "prompt": "2-color cards that care about +1/+1 counters",
  "count": 10
}
```

### Feedback

| Method | Path | Description |
|--------|------|-------------|
| POST | `/decks/{id}/feedback` | Submit thumbs up/down on a card |
| GET | `/decks/{id}/feedback` | Get all feedback for a deck |

**POST /decks/{id}/feedback** request body:
```json
{
  "card_id": "uuid",
  "feedback": "up | down",
  "reason": "too expensive for this curve"
}
```

### Preferences (Account-Level)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/preferences` | List all account preferences |
| POST | `/preferences` | Add a preference |
| DELETE | `/preferences/{id}` | Remove a preference |

**POST /preferences** request body:
```json
{
  "preference_type": "pet_card | avoid_card | avoid_archetype | general",
  "card_id": "uuid | null",
  "description": "Always try to include Monologue Tax in white decks"
}
```

## Response Format

All responses follow a consistent envelope:

```json
{
  "data": { ... },
  "meta": {
    "total": 100,
    "limit": 20,
    "offset": 0
  }
}
```

Error responses:

```json
{
  "error": {
    "code": "CARD_NOT_FOUND",
    "message": "Card with ID xyz not found in local database"
  }
}
```

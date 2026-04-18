# Collection Feature — Plan

Collection ingestion from Moxfield CSV, collection-constrained card suggestions. Track multiple named collections per account, filter AI suggestions to owned cards with a relevance-score floor.

## Locked decisions

1. **Multiple named collections** per account (paper binder, online, trade box, etc.). Default collection per account.
2. **Strict filter** on retrieval: non-owned cards are dropped. No score boost / mixed output.
3. **Two-level toggle**: account-level default + per-deck override (`off | inherit | on`).
4. **Merge** is the default import mode; `replace` opt-in.
5. **Printing-level storage** (set_code + collector_number + foil). Retrieval joins to `oracle_id` so any owned printing counts as "card available". Required for CSV round-trip anyway.

## Data model

```sql
CREATE TABLE collections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id  UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, name)
);

CREATE TABLE collection_cards (
    collection_id     UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    card_id           UUID NOT NULL REFERENCES cards(id),
    set_code          TEXT NOT NULL DEFAULT '',      -- from CSV, round-trip
    collector_number  TEXT NOT NULL DEFAULT '',      -- from CSV, round-trip
    foil              BOOL NOT NULL DEFAULT FALSE,
    quantity          INT  NOT NULL DEFAULT 1 CHECK (quantity > 0),
    condition         TEXT,
    language          TEXT,
    tags              TEXT[] NOT NULL DEFAULT '{}',
    purchase_price    NUMERIC,
    last_modified     TIMESTAMPTZ,
    PRIMARY KEY (collection_id, card_id, set_code, collector_number, foil)
);
CREATE INDEX idx_collection_cards_card ON collection_cards(card_id);

ALTER TABLE accounts
    ADD COLUMN collection_suggestions_enabled BOOL NOT NULL DEFAULT FALSE,
    ADD COLUMN collection_threshold REAL NOT NULL DEFAULT 0.3,
    ADD COLUMN default_collection_id UUID REFERENCES collections(id) ON DELETE SET NULL;

ALTER TABLE decks
    ADD COLUMN collection_mode TEXT NOT NULL DEFAULT 'inherit'
        CHECK (collection_mode IN ('off', 'inherit', 'on')),
    ADD COLUMN collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
    ADD COLUMN collection_threshold REAL;
```

**Printing match:** current `cards` table is seeded from Scryfall `oracle_cards` bulk (one row per unique card, no `collector_number`). Phase 1 resolves CSV rows by **name only** (`card_service.resolve_card_by_name`). CSV `Edition` + `Collector Number` are stored on `collection_cards` for round-trip preservation — not used for matching. Future: load `default_cards` bulk to enable true printing-level matching. Unresolved rows returned in import response for user to fix.

## API

```
GET    /api/v1/accounts/{id}/collections
POST   /api/v1/accounts/{id}/collections              body: {name}
PATCH  /api/v1/accounts/{id}/collections/{cid}        body: {name}
DELETE /api/v1/accounts/{id}/collections/{cid}

GET    /api/v1/collections/{cid}/cards?page=&q=&color=
POST   /api/v1/collections/{cid}/cards                single add (search-bar)
PATCH  /api/v1/collections/{cid}/cards/{card_id}      qty/foil/condition
DELETE /api/v1/collections/{cid}/cards/{card_id}

POST   /api/v1/collections/{cid}/import               body: {csv, mode: merge|replace}
GET    /api/v1/collections/{cid}/export               text/csv
```

All responses use `DataResponse[T]`. Errors use `ErrorResponse` code/message.

## Moxfield CSV format

```
"Count","Tradelist Count","Name","Edition","Condition","Language","Foil","Tags",
"Last Modified","Collector Number","Alter","Proxy","Purchase Price"
"1","1","Sol Ring","c19","Near Mint","English","","","2026-04-04 14:39:47","255","False","False","2.50"
```

Round-trip requirement: export must produce rows re-importable without data loss (preserve Tags, Condition, Language, Foil, Purchase Price).

## Retrieval

`retrieve_candidates` gains optional `collection_filter: CollectionFilter`:

```python
@dataclass
class CollectionFilter:
    owned_oracle_ids: set[UUID]
    min_score: float  # drop candidates below this final weighted score
```

Applied at:
- `_search_tags` / `_search_fts` — `AND oracle_id = ANY($owned::uuid[])`
- Qdrant — `HasIdCondition` with owned `card_id` set
- Post-scoring — drop entries `< min_score` (no padding)

Resolution per build:
- `deck.collection_mode = 'off'` → no filter
- `'inherit'` → use account default (`default_collection_id` + `collection_suggestions_enabled`)
- `'on'` → use `deck.collection_id`
- Threshold: `deck.collection_threshold ?? account.collection_threshold`

## Frontend

Nav tab `/collections`:
- `/collections` — list of collections (name, total cards, value)
- `/collections/new` — create
- `/collections/[id]` — card grid, search bar add, per-row qty/foil/remove, CSV import/export buttons
- `/collections/[id]/import` — paste CSV or upload, preview, merge/replace, show unresolved

Deck creation form — select: off / inherit / specific collection + threshold override.
Build wizard + chat — threshold slider 0.0–0.8 when collection active; collection selector.
Preferences page — default collection dropdown + default threshold slider + master toggle.

## Phases

### Phase 1 — Schema + service + CRUD endpoints (backend)
- Tables, migrations
- `models/collections.py`
- `services/collection_service.py` (parser, CRUD, import merge/replace, export, printing resolver)
- `routers/collections.py`
- Tests: parser unit, CRUD integration, import/export round-trip, unresolved handling

### Phase 2 — Single card add/remove / search bar
- Endpoint `POST /collections/{cid}/cards` with name or scryfall_id
- Endpoint `DELETE /collections/{cid}/cards/{card_id}`
- Tests

### Phase 3 — `/collections` frontend tab
- List + detail pages, CSV import/export UI, search add, row edit

### Phase 4 — Retrieval `collection_filter` + threshold floor
- `CollectionFilter` dataclass + wiring through `retrieve_candidates`
- SQL filter in `_search_tags` / `_search_fts`
- Qdrant `HasIdCondition` path
- Post-score floor
- Tests (real DB, mocked Qdrant)

### Phase 5 — Account preference + per-deck toggle + build wizard UI
- `collection_suggestions_enabled`, `default_collection_id`, `collection_threshold` on accounts
- `collection_mode`, `collection_id`, `collection_threshold` on decks
- Preferences page controls
- Deck creation select
- Build wizard threshold slider + collection selector

## Open items (defer)

- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Collection sharing / import from other users
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings

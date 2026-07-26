# Moxfield Binder URL Import — Design

Date: 2026-07-26
Status: Approved

## Summary

Allow importing a public Moxfield **binder** (e.g.
`https://moxfield.com/binders/LbwVB1hSiU2THiRQeR2QlQ`) into collections by
pasting a link, instead of requiring a CSV export. One-shot import; the link is
not stored and no re-sync state is kept (a manual re-import with `replace`
mode serves as a poor-man's re-sync).

Two flows:

- **Flow A — into an existing collection:** the `/collections/[id]/import`
  page gains a "Moxfield link" source next to the CSV formats, with the same
  merge/replace mode picker.
- **Flow B — create a new collection from the link:** the `/collections/new`
  page gains an "import from a Moxfield link" section that creates a
  collection named after the binder and fills it.

## Verified upstream API

Probed live against a real public binder on 2026-07-26:

- `GET {moxfield_base_url}/v1/trade-binders/{publicId}?pageNumber=N&pageSize=100`
  - `moxfield_base_url` defaults to `https://api2.moxfield.com` (existing config).
  - Requires curl_cffi Chrome impersonation (Cloudflare), same as deck import.
  - Paginated: `pageNumber`, `pageSize` (max 100), `totalPages`,
    `totalResults` (row count), `data` (entries). `totalOverall` is the sum of
    quantities.
  - Binder metadata at `tradeBinder.{name, description, visibility, publicId}`.
- Entry shape (fields we consume):

```json
{
  "quantity": 2,
  "condition": "nearMint",
  "finish": "nonFoil",
  "isFoil": false,
  "purchasePrice": 0.09,
  "lastUpdatedAtUtc": "2025-06-19T15:41:18.607Z",
  "language": { "code": "en", "name": "English" },
  "card": {
    "scryfall_id": "a1aa3501-5738-4063-a7f4-51d2600b0041",
    "set": "tdm",
    "cn": "133",
    "name": "Zurgo's Vanguard"
  }
}
```

## Architecture

Follows the established deck URL-import pattern
(`deck_url_import_service.py` → `import_service.import_parsed_entries`):
a thin source-specific fetch/translate layer delegating to a shared
persistence pipeline.

### New service: `collection_url_import_service.py`

- **URL parsing:** regex
  `^https?://(?:www\.)?moxfield\.com/binders/(?P<id>[A-Za-z0-9_-]+)/?`
  (case-insensitive, trailing path allowed) → binder public id.
  Raises `UnsupportedBinderUrlError` otherwise.
- **Fetch:** loops `pageNumber` from 1 to `totalPages` at `pageSize=100`,
  accumulating entries. Safety cap of 200 pages (20k rows) with a clear
  error. Politeness delay between pages via new config
  `moxfield_binder_page_delay_seconds` (default 0.25). Per-request timeout
  30s. Production client: curl_cffi `AsyncSession(impersonate="chrome")`;
  tests inject `httpx.AsyncClient` with a mock transport (both expose
  `.get()/.aclose()`), reusing the `_make_client`/`_close_client` approach
  from `deck_url_import_service`.
- **Errors:** all upstream failures raise `BinderFetchError`:
  - Cloudflare challenge (reuse `_looks_like_cloudflare` heuristics) →
    message suggesting the CSV export fallback.
  - 401/403 → binder is private or rate-limited.
  - 404 → binder not found.
  - Non-JSON body or ≥400 status → generic fetch error.

### Entry → `ParsedCollectionRow` mapping

| Row field          | Binder entry source                                      |
| ------------------ | -------------------------------------------------------- |
| `name`             | `card.name`                                              |
| `quantity`         | `quantity`, clamped to ≥ 1                               |
| `set_code`         | `card.set`                                               |
| `collector_number` | `card.cn`                                                |
| `foil`             | `isFoil` or `finish` ∈ {`foil`, `etched`}                |
| `condition`        | camelCase → Title Case (`nearMint` → `Near Mint`)        |
| `language`         | `language.name` (`English`); `None` when absent          |
| `tags`             | `[]` (binders carry no tags)                             |
| `purchase_price`   | `Decimal(str(purchasePrice))` when > 0, else `None`      |
| `last_modified`    | parsed from `lastUpdatedAtUtc`                           |
| `scryfall_id`      | `card.scryfall_id` — exact resolution, no name guessing  |

### Refactor: shared `import_rows` in `collection_service.py`

Extract everything in `import_csv` after parsing into:

```python
async def import_rows(
    pool: asyncpg.Pool,
    collection_id: UUID,
    rows: list[ParsedCollectionRow],
    mode: str,
    source: str = "csv",
) -> CollectionImportResponse: ...
```

(resolve via Scryfall ID with name fallback → assert collection exists →
merge/replace transaction → log → response.) `import_csv` becomes
parse-then-delegate; behavior and existing tests unchanged.

## API

### Flow A — `POST /api/v1/collections/{collection_id}/import-url`

Body (`CollectionUrlImportRequest`):

```json
{ "url": "https://moxfield.com/binders/<id>", "mode": "merge" }
```

- `url`: string, required. `mode`: `"merge" | "replace"`, default `"merge"`.
- Response: `DataResponse[CollectionImportResponse]` — identical shape to
  the CSV import (`imported`, `updated`, `removed`, `unresolved`).
- Errors: 404 `COLLECTION_NOT_FOUND`; 422 `UNSUPPORTED_URL`;
  502 `UPSTREAM_FETCH_FAILED`.

### Flow B — `POST /api/v1/me/collections/import-url`

Authenticated (in `routers/me.py`). Body (`CollectionFromUrlRequest`):

```json
{ "url": "https://moxfield.com/binders/<id>", "name": null }
```

- `name`: optional override; defaults to the binder's Moxfield name, then to
  `"Moxfield binder"` when blank.
- Behavior: fetch binder → create collection for the account → import rows
  (fresh collection, so effectively replace semantics).
- Response: `201 DataResponse[CollectionFromUrlResponse]` with
  `{ collection: CollectionResponse, import: CollectionImportResponse }`.
- Errors: 409 `DUPLICATE_COLLECTION`; 422 `UNSUPPORTED_URL`;
  502 `UPSTREAM_FETCH_FAILED`.

## Frontend

- **`/collections/[id]/import`:** a "Source" toggle at the top — *CSV* |
  *Moxfield link*. CSV keeps the current UI (format picker, upload/paste).
  Moxfield link shows a URL input; the merge/replace mode picker and the
  result view are shared and unchanged.
- **`/collections/new`:** an "or import from a Moxfield link" section with a
  URL input and an optional name field (placeholder notes it defaults to the
  binder name). On success, redirect to `/collections/{newId}`; duplicate
  name surfaces the 409 message inline.
- `lib/api.ts`: `importCollectionUrl(id, {url, mode})` and
  `createCollectionFromUrl({url, name?})`; `lib/types.ts` gains the matching
  request/response types.

## Edge cases

- **Empty binder:** flow A returns `imported=0`; flow B still creates the
  (empty) collection using the binder name.
- **Unresolvable rows:** exact `scryfall_id` lookup first; fall back to name
  resolution (existing `_resolve_rows`); misses land in `unresolved`.
- **Duplicate printings within a binder:** the existing
  `(collection_id, card_id, set_code, collector_number, foil)` upsert
  already merges them.
- **Malformed/unsupported URL** (deck links, Archidekt, etc.): 422 with a
  message naming the expected binder URL shape.

## Testing

New `backend/tests/test_collection_url_import.py`, mirroring
`test_deck_url_import.py`:

- URL regex: valid binder URLs (with/without www, trailing slash/slug),
  rejected non-binder URLs.
- Entry mapping: condition title-casing, foil/etched, language, price,
  scryfall_id passthrough.
- Pagination: mock client serving multi-page sequences; entries accumulated
  in order; safety cap error.
- Errors: Cloudflare HTML → friendly message; 403 → private; 404 → not
  found; non-JSON → fetch error.
- Flow A: merge into an existing collection; 404 for unknown collection.
- Flow B: creates a collection named after the binder and imports; name
  override; 409 on duplicate name.
- Existing `test_collections.py` (CSV import) must pass unchanged after the
  `import_rows` refactor.

Frontend: manual verification (the CSV import page has no component tests
today; we match that coverage level).

## Out of scope

- Storing the binder URL / automatic or button-driven re-sync.
- Archidekt or other collection sources.
- Importing binder prices/totals beyond per-row `purchasePrice`.

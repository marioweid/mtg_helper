# Moxfield Binder URL Import — Implementation Plan

Date: 2026-07-26
Spec: `docs/superpowers/specs/2026-07-26-moxfield-binder-url-import-design.md` (approved)

Constraints (AGENTS.md): ≤100 lines/function, cyclomatic complexity ≤8,
≤5 positional params, 100-char lines, absolute imports, Google docstrings,
plain asyncpg `$1` params, `DataResponse`/`ErrorResponse` envelope.

## Task 1 — Backend: shared `import_rows` refactor

`backend/src/mtg_helper/services/collection_service.py`

- Extract resolve + assert-exists + merge/replace transaction + logging from
  `import_csv` into `import_rows(pool, collection_id, rows, mode, source="csv")`
  returning `CollectionImportResponse`.
- `import_csv` becomes: parse via `parse_collection_csv` → delegate.
- **Verify:** `uv run pytest tests/test_collections.py -q` passes unchanged.

## Task 2 — Backend: `collection_url_import_service.py`

New file, mirroring `deck_url_import_service.py` structure:

- `_MOXFIELD_BINDER_URL` regex → `parse_binder_url(url) -> str`;
  `UnsupportedBinderUrlError(ValueError)`, `BinderFetchError(RuntimeError)`.
- `_make_client()` / `_close_client()` — copy the curl_cffi factory pattern
  (impersonate chrome, 30s timeout).
- `fetch_moxfield_binder(binder_id, *, client) -> FetchedBinder` where
  `FetchedBinder` is a dataclass: `binder_id`, `name`, `rows:
  list[ParsedCollectionRow]`. Paginates `pageNumber=1..totalPages` at
  `pageSize=100`; cap 200 pages (`BinderFetchError` when exceeded);
  `asyncio.sleep(settings.moxfield_binder_page_delay_seconds)` between pages.
- Error translation identical in spirit to deck service: Cloudflare HTML →
  CSV-fallback message; 401/403 → private/rate-limited; 404 → not found;
  non-JSON / other ≥400 → generic.
- Entry translation helpers (small, individually testable):
  `_condition_title()` (camelCase → Title Case), `_entry_foil()`,
  `_entry_price()` (>0 else None), `_entry_row()` → `ParsedCollectionRow`.
- `import_from_url(pool, collection_id, url, mode, *, client=None)` — flow A:
  parse → fetch → `collection_service.import_rows(..., mode, source="moxfield-url")`.
- `import_new_from_url(pool, url, account_id, *, name=None, client=None)` —
  flow B: fetch → `create_collection` (name override → binder name →
  `"Moxfield binder"`) → `import_rows(..., "replace", ...)`.

`backend/src/mtg_helper/config.py`: add
`moxfield_binder_page_delay_seconds: float = 0.25`.

## Task 3 — Backend: models

`backend/src/mtg_helper/models/collections.py`:

- `CollectionUrlImportRequest`: `url: str` (min_length 1, max_length 2048),
  `mode: Literal["merge", "replace"] = "merge"`.
- `CollectionFromUrlRequest`: `url: str`, `name: str | None`
  (min_length 1, max_length 200).
- `CollectionFromUrlResponse`: `collection: CollectionResponse`,
  `import_: CollectionImportResponse = Field(alias="import")` with
  `model_config = ConfigDict(populate_by_name=True)` (`import` is a Python
  keyword; JSON field stays `import` per spec).

## Task 4 — Backend: endpoints

- `routers/collections.py`:
  `POST /{collection_id}/import-url` → `DataResponse[CollectionImportResponse]`.
  Mapping: `CollectionNotFoundError` → 404 `COLLECTION_NOT_FOUND`;
  `UnsupportedBinderUrlError` → 422 `UNSUPPORTED_URL`;
  `BinderFetchError` → 502 `UPSTREAM_FETCH_FAILED`.
- `routers/me.py`:
  `POST /collections/import-url` (201) →
  `DataResponse[CollectionFromUrlResponse]`. Uses `CurrentAccount`.
  Additionally `DuplicateCollectionNameError` → 409 `DUPLICATE_COLLECTION`.
- `Annotated` dependency style, response models set, no `...` defaults
  (fastapi skill conventions; matches existing code).

## Task 5 — Backend: tests

New `backend/tests/test_collection_url_import.py` mirroring
`test_deck_url_import.py` (httpx `MockTransport`-injected clients,
`unittest.mock.patch` around `collection_service.import_rows` /
`create_collection` for the DB-touching orchestration):

1. `parse_binder_url`: basic, no-www, trailing slash, trailing path;
   rejects raw id, foreign host, `/decks/` URL.
2. Entry mapping: condition title-casing, foil via `isFoil` and
   `finish: etched`, language name, price 0 → None, scryfall_id passthrough,
   quantity clamp.
3. Pagination: 3-page mock sequence accumulates all entries; binder name
   captured; cap-exceeded → `BinderFetchError`.
4. Errors: Cloudflare HTML (403) → CSV-fallback message; plain 403 →
   private; 404 → not found; invalid JSON → fetch error.
5. Flow A: delegates to `import_rows` with parsed rows + mode.
6. Flow B: creates collection with binder name, imports with replace; name
   override wins; blank binder name → `"Moxfield binder"`.

**Verify:** `uv run pytest -q`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run ty check src/` from `backend/`.

## Task 6 — Frontend: API client + types

- `frontend/lib/types.ts`: `CollectionUrlImportRequest`,
  `CollectionFromUrlRequest`, `CollectionFromUrlResponse`
  (`{ collection: CollectionResponse; import: CollectionImportResponse }`).
- `frontend/lib/api.ts`: `importCollectionUrl(id, body)` → POST
  `/collections/{id}/import-url`; `createCollectionFromUrl(body)` → POST
  `/me/collections/import-url` (201).

## Task 7 — Frontend: import page source toggle

`frontend/app/collections/[id]/import/page.tsx`:

- `source: "csv" | "link"` state; "Source" section with two toggle cards
  matching the existing format-picker style.
- `link` source: URL input (placeholder
  `https://moxfield.com/binders/...`), format picker + textarea/upload
  hidden; submit calls `importCollectionUrl`; same mode picker and result
  view (response shape is identical).
- Map `UNSUPPORTED_URL` and `UPSTREAM_FETCH_FAILED` error codes to friendly
  inline messages.

## Task 8 — Frontend: `/collections/new` link section

`frontend/app/collections/new/page.tsx`:

- Divider "or import from a Moxfield link": URL input + optional name input
  (placeholder "Defaults to the binder name") + submit button.
- Success → `router.push(`/collections/${created.collection.id}`)`;
  `DUPLICATE_COLLECTION` → inline error, keeping entered values.

## Task 9 — Final verification

- Backend: full `pytest -q`, `ruff check`, `ruff format`, `ty check src/`.
- Frontend: `pnpm tsc --noEmit` (or repo's typecheck script) + any existing
  vitest run.
- Manual smoke (optional, user-run): import the real binder into a test
  collection in merge mode.

## Task order & commits

1. Tasks 1–5 (backend) — one commit: `feat: import collections from Moxfield binder URLs`
2. Tasks 6–8 (frontend) — one commit: `feat: Moxfield link import UI for collections`
3. Task 9 verification before each commit.

# ManaBox Collection Import Design

**Date:** 2026-07-23

## Goal

Support explicit Moxfield and ManaBox CSV formats when importing cards into a collection, using the
existing merge/replace workflow and import result screen.

## Import format selection

The collection import page adds a required format selector with two options:

- Moxfield, selected by default for backward compatibility.
- ManaBox.

The selected format is sent as `format` in the existing import request. The explanatory copy and
CSV placeholder change to match the selected format. Uploading and pasting CSV text continue to use
the same input, and merge/replace behavior remains independent of format.

The API model accepts `moxfield` or `manabox` and defaults a missing value to `moxfield`, preserving
compatibility with existing callers.

## Parsing architecture

The collection service keeps format-specific parsers that normalize rows into the existing shared
collection-row structure:

- `parse_moxfield_csv`
- `parse_manabox_csv`

The import service chooses the parser from the explicit request format. It does not auto-detect
headers or silently switch formats. Missing required headers produce a format-specific parse error.

### ManaBox column mapping

| ManaBox column | Collection field | Behavior |
| --- | --- | --- |
| `Name` | name | Required |
| `Quantity` | quantity | Required; non-positive rows are skipped |
| `Set code` | set code | Preserved |
| `Collector number` | collector number | Preserved |
| `Foil` | foil | `foil` and `etched` are true; `normal` is false |
| `Condition` | condition | Preserved |
| `Language` | language | Preserved |
| `Scryfall ID` | resolver identifier | Exact match attempted first |

ManaBox ID, set name, rarity, misprint, altered, purchase-price currency, and added date are ignored
because the current collection model does not need or store them.

## Card resolution

Normalized rows may include an optional Scryfall ID.

1. If a valid Scryfall ID is present, resolve it directly against the local card database.
2. If the ID is missing, malformed, or absent locally, fall back to the existing card-name
   resolver.
3. If both methods fail, report the card name through the existing unresolved list.

Moxfield rows continue to use name resolution unless their normalized structure gains an ID in a
future change.

## Purchase prices

CSV purchase-price values are ignored for both Moxfield and ManaBox imports. Current linked market
prices continue to come from card data.

- Merge imports preserve any purchase price already stored on an existing collection row.
- Newly inserted rows have no purchase price.
- Replace imports create replacement rows without purchase prices.
- Manual purchase-price editing and existing stored values are otherwise unchanged.

## API and errors

The existing collection import endpoint remains unchanged:

`POST /api/v1/collections/{collection_id}/import`

Its request gains `format: "moxfield" | "manabox"`. Response fields and error envelopes do not
change. Invalid format-specific headers or empty files return the existing `PARSE_ERROR` response
with a message naming the selected format's required columns.

## Scope and validation

No schema migration is required. The change is limited to the collection import request model,
router/service plumbing, normalized parsing and resolution, frontend request type, and collection
import page.

Validation will use backend Ruff and type checks plus frontend lint, TypeScript, and production
build checks. Per the established request, no tests will be added or run.

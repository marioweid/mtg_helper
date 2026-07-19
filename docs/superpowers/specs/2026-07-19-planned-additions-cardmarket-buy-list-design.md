# Planned Additions Cardmarket Buy List

## Goal

Let a user turn planned deck additions into a Cardmarket-compatible buy list while choosing
which binders may supply cards. Collections such as a proxy binder can be excluded from the
ownership calculation without changing deck plans or collection data.

## Existing Behavior

- Planned additions are stored separately from the physical deck in `deck_card_plans`.
- Each planned addition exposes collection ownership and an optional source-collection choice.
- The existing physical-deck **Buy list** export calculates physical deck deficits across all
  collections and copies `<quantity> <card name>` lines to the clipboard.

The new export is separate from the physical-deck Buy list because planned additions do not yet
belong to the physical deck.

## User Experience

The **Planned additions** heading in the shared planned-changes panel gains a **Create buy list**
button. The panel is shared by deck detail, builder, coach, and playtest screens, so the action is
available everywhere the planned checklist appears.

Selecting the action opens a dialog titled **Count cards from these binders**:

- Every binder is checked by default.
- **Select all** and **Select none** shortcuts are available.
- Unchecked binders do not reduce the quantity to buy.
- Selecting no binders is valid and exports every planned addition at its full quantity.
- Selections apply only to the current export and do not modify the source-collection dropdowns.

The dialog has **Cancel** and **Copy buy list** actions. Copying requests a fresh server-side
calculation and writes the returned text to the clipboard. A successful non-empty export shows
`Shopping list copied.` An empty result shows `You already own all planned additions.`

API or clipboard failures leave the dialog open and display an actionable error. The export does
not mutate planned changes, physical deck composition, or collection inventory.

## API Contract

Add a read-only calculation endpoint:

```text
POST /api/v1/decks/{deck_id}/planned-changes/shopping-list
Content-Type: application/json

{
  "collection_ids": ["<binder UUID>"]
}
```

The response is `text/plain`, using the existing Cardmarket wants-list format:

```text
1 Doubling Season
2 Sol Ring
```

Lines are sorted alphabetically by card name. An empty result is a successful response with an
empty body.

The server returns:

- `404` when the deck does not exist or is not owned by the current account.
- `422` when any supplied collection ID is not owned by the current account.

The request is a `POST` because the selected binder IDs are supplied as a body, but the operation
is read-only and has no persistent side effects.

## Calculation Rules

1. Load only `addition` rows from `deck_card_plans` for the owned deck.
2. Group planned quantities by oracle identity so alternate printings do not create duplicate
   shopping-list entries.
3. Sum inventory from only the selected, account-owned collections, also by oracle identity.
4. Calculate `max(0, grouped planned quantity - selected inventory quantity)`.
5. Omit fully covered cards and output the remaining deficits alphabetically as
   `<quantity> <card name>`.

Planned cuts, physical deck cards, unselected collections, and the optional source binder stored
on a plan do not affect this calculation.

## Components and Responsibilities

### Backend model

A small Pydantic request model validates `collection_ids` as a list of UUIDs. Duplicate IDs are
harmless but should be normalized before querying.

### Planned-change service

The service owns authorization, selected-collection validation, oracle-level aggregation, deficit
calculation, and text formatting. Keeping this logic server-side prevents stale client ownership
data and makes the behavior reusable and testable.

### Deck router

The planned-changes router exposes the endpoint and maps existing ownership/validation errors to
the standard API error shape while returning successful output as `text/plain`.

### Frontend API client

The client sends the selected collection IDs and returns the plain-text response. API failures are
converted to the existing `ApiError` type.

### Planned changes panel

The shared panel owns dialog visibility, checked binder IDs, loading state, error display, and the
clipboard action. Opening the dialog resets the selection to all currently loaded binders.

## Testing

Backend tests cover:

- Full planned quantity with no binders selected.
- Fully covered and partially covered additions.
- Checked binders reducing the deficit while unchecked binders are ignored.
- Alternate printings matching by oracle identity.
- Multiple planned printings grouped without subtracting the same inventory twice.
- Planned cuts and physical deck contents being ignored.
- Empty planned additions producing an empty response.
- Other accounts' collections never contributing inventory.
- Unknown/unowned decks returning `404`.
- Any invalid or unowned selected collection returning `422`.
- Alphabetical Cardmarket output and correct quantities.

Frontend validation covers TypeScript, lint, existing component tests, and the production build.
The dialog interaction should be smoke-tested for default selections, select-all/select-none,
empty-result messaging, successful clipboard copy, and retained state on failure.

## Non-Goals

- Persisting preferred binder exclusions between exports.
- Modifying the existing physical-deck Buy list.
- Creating a Cardmarket wishlist through an external Cardmarket API.
- Selecting editions, conditions, languages, prices, or foil preferences.
- Mutating binder inventory or completing planned additions during export.

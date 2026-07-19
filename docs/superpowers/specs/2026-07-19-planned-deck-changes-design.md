# Planned Deck Changes Design

## Goal

Let users design upgrades without immediately changing the application's record of the physical
deck. Cards that should enter the deck are **Planned additions**. Cards that remain physically in
the deck but should leave later are **Planned cuts**.

The workflow is available anywhere the application can currently add, cut, or swap a main-deck
card. Users complete moves one copy at a time as cards become available. Collection selection is
an optional inventory helper, not a prerequisite for completing a move.

## Core Invariant

`deck_cards` remains the only source of truth for the physical main deck. Pending changes are
stored separately and are never implicitly included in deck metrics, legality checks, simulation,
AI analysis, snapshots, exports, or other deck-composition queries.

A planned addition is not in the physical deck until it is completed. A planned cut remains in the
physical deck until it is completed. Projected counts and compositions must use an explicitly named
planned-deck calculation; physical composition is the default everywhere.

Commander and partner cards are outside this workflow.

## User Experience

Card actions in a deck context default to **Plan addition** and **Plan cut**. The secondary actions
**Add now** and **Remove now** remain available for immediate physical edits. Swap actions default
to creating a paired planned cut and planned addition, with an immediate swap as a secondary
action.

Every deck screen exposes the same **Planned changes** checklist and displays physical and planned
totals, such as `100 physical -> 100 planned`. Physical cards with pending cuts remain in their
normal deck location and receive a **Planned cut** badge. Planned additions appear in the checklist
and not in the physical card list.

The checklist has compact rows grouped under **Planned additions** and **Planned cuts**. Each row
contains:

- card name and pending quantity;
- the existing collection ownership badge for additions, including each matching collection and
  its available quantity;
- a small collection dropdown, empty by default;
- a one-copy completion control;
- controls to change the pending quantity or cancel the plan.

The optional dropdown means **Take from collection** for an addition and **Place in collection**
for a cut. Its selection is saved with the planned row, but changing it alone does not change deck
or collection quantities. Completing a copy performs the physical and optional inventory move.
An empty dropdown changes only the physical deck.

An addition dropdown lists only collections that currently contain the exact card, alongside the
empty option. A cut dropdown lists all of the user's collections because any can receive the card.

For plans with multiple copies, each completion reduces the pending quantity by one. A user can
therefore complete part of a plan and leave the rest pending. The API also supports completing a
larger bounded quantity so future batch controls do not require a new data model.

## Cross-App Coverage

The planning behavior replaces the default mutation action in:

- deck overview and card details;
- deck builder and expandable deck bar;
- coach and deck-doctor recommendations;
- playtest and optimizer suggestions;
- swap suggestions and mana-fix recommendations;
- deck card search, compact lists, and category views.

Collection card rows add a **Plan for deck...** action. Selecting a deck creates a planned addition
and keeps the collection unchanged until completion. The existing ownership badge is reused rather
than creating a second collection indicator.

Deck imports continue to describe the current physical deck. New and imported decks can use the
same planning actions for all subsequent changes.

## Data Model

Add a `deck_card_plans` table with:

- `id UUID PRIMARY KEY`;
- `deck_id UUID NOT NULL` referencing `decks` with cascade deletion;
- `card_id UUID NOT NULL` referencing `cards`;
- `direction TEXT NOT NULL` constrained to `addition` or `cut`;
- `quantity INTEGER NOT NULL` constrained to a positive value;
- `collection_id UUID NULL` referencing `collections` with `ON DELETE SET NULL`;
- `created_at` and `updated_at` timestamps;
- a unique constraint on `(deck_id, card_id)`.

One card has at most one net pending direction in a deck. Planning more copies in the same direction
increments the pending quantity. Planning the opposite direction offsets the existing quantity;
equal quantities cancel the plan, and any remainder changes to the new net direction. This prevents
simultaneous, contradictory addition and cut rows for the same printing.

A cut quantity cannot exceed the card's current physical main-deck quantity. The selected
collection must belong to the deck owner's account. Collection selection does not reserve cards;
availability is revalidated when the move is completed.

## API

All endpoints use the existing `DataResponse[T]` and `ErrorResponse` envelopes under `/api/v1`.

- `GET /decks/{deck_id}/planned-changes` lists pending additions and cuts with card display data,
  ownership memberships, physical quantity, and projected quantity.
- `POST /decks/{deck_id}/planned-changes` creates or offsets a plan using card Scryfall ID,
  direction, and quantity.
- `PATCH /decks/{deck_id}/planned-changes/{plan_id}` changes pending quantity or the optional
  collection selection.
- `DELETE /decks/{deck_id}/planned-changes/{plan_id}` cancels a pending plan without changing the
  physical deck or inventory.
- `POST /decks/{deck_id}/planned-changes/{plan_id}/complete` completes a positive quantity bounded
  by the pending quantity. The frontend completes one copy by default.

The deck-detail response exposes physical and planned totals plus the pending-change list, or loads
the same model through the list endpoint when a screen already fetches deck data separately. It
does not merge planned additions into `cards` or remove planned cuts from `cards`.

## Completion Transactions

Completion locks the plan row and relevant deck and collection rows in one database transaction.

For an addition, completion:

1. revalidates the optional selected collection and its exact card quantity;
2. decreases or deletes that collection-card row when a collection is selected;
3. inserts or increments the physical `deck_cards` row;
4. decreases the pending quantity and deletes the plan at zero.

For a cut, completion:

1. revalidates that the physical deck contains the requested quantity;
2. decreases or deletes the physical `deck_cards` row;
3. inserts or increments the exact card in the selected collection when one is selected;
4. decreases the pending quantity and deletes the plan at zero.

If collection metadata not represented by the physical deck, such as foil status or condition, is
unknown for a cut, the collection service uses its existing defaults. The application does not
invent foil, condition, language, or purchase data.

An immediate add or removal uses the physical mutation path and reconciles related plans. Adding
now consumes pending additions for that card first. Removing now consumes pending cuts first. Any
remaining cut is clamped to the physical quantity so a plan can never promise to cut unavailable
copies.

## Calculation Boundaries

Existing deck services continue to read only `deck_cards`; their queries do not join
`deck_card_plans`. This preserves current behavior for:

- deck counts, categories, curve, type distribution, and scorecards;
- commander legality, color identity, brackets, and game-changer checks;
- goldfishing, playtest simulation, optimization input, and snapshots;
- AI context, retrieval filters, coach analysis, cuts, and replacement candidates;
- deck comparison and exports.

The planned total is `physical total + pending additions - pending cuts`. Any future projected
analysis must opt into a dedicated planned-composition service and name that scope at the call site.
No shared deck loader gains a boolean flag whose default could be misunderstood.

Collection ownership badges reflect current collection quantities. Pending additions do not
reserve collection cards, and pending cuts do not appear as collection inventory before completion.

## Errors and Concurrency

The service returns stable errors for a missing plan, an unowned deck or collection, an invalid
direction or quantity, insufficient physical deck quantity, and insufficient selected-collection
quantity. A failed completion leaves the plan, deck, and collection unchanged.

Row locking and transaction-scoped validation prevent two completions from consuming the same deck
or collection copy. If a collection is deleted after selection, `ON DELETE SET NULL` leaves the
plan usable with an empty selection. If an ownership quantity changes before completion, the UI
refreshes the ownership badge after the service rejects the stale move.

## Testing and Acceptance Criteria

Backend model, service, and API tests verify:

- creating, incrementing, offsetting, cancelling, and partially completing plans;
- cut quantities cannot exceed the physical main-deck quantity;
- pending changes do not alter physical deck responses or any existing calculation input;
- projected totals apply additions and cuts correctly without mutation;
- addition and cut completion with no collection selected;
- atomic collection decrement for additions and increment for cuts;
- insufficient inventory and concurrent completion attempts leave all state consistent;
- collection ownership validation and deleted-collection behavior;
- direct physical actions reconcile related pending plans;
- commander and partner cards cannot be planned through these endpoints.

Frontend tests verify:

- planning is the default and immediate mutation remains available;
- shared badges, physical/planned totals, and the inline checklist render consistently;
- the existing ownership badge displays every matching collection and quantity;
- collection selection persists without moving inventory;
- one-copy completion, partial quantities, cancellation, and error refresh behavior;
- each existing mutation surface routes through the shared planning action.

The change is accepted when focused backend and frontend tests pass together with `ruff check`,
`ruff format --check`, `ty check`, TypeScript type checking, and the existing regression suites
covering decks, collections, builder roles, swaps, optimizer behavior, and snapshots.

## Out of Scope

This version does not plan commander or partner changes, reserve collection inventory, add purchase
or shipping statuses, create a movement-history ledger, infer missing printing attributes, or make
projected composition the default input to analysis tools.

# Deck Revision History

**Date:** 2026-07-22
**Status:** Approved design
**Scope:** Planned-change application, durable revision history, and snapshot integration

## Objective

Replace card-by-card planned-change completion with meaningful deck revisions. A revision applies a
user-selected subset of planned additions and cuts atomically, preserves the intent and provenance
of those changes, and captures reconstructable before and after deck states. Unselected plans remain
pending, allowing users to apply newly acquired cards without committing speculative cuts.

Deck revisions become the primary history experience. Existing manual and automatic stage snapshots
remain available as secondary checkpoints.

## Design Principles

- One revision represents one intentional deck update.
- Applying selected plans is all-or-nothing.
- Completed change details are immutable and remain understandable after plans are deleted.
- Before and after compositions are reconstructable without replaying events.
- Unselected plans and unrelated collection inventory are untouched.
- Existing direct deck mutations remain supported and appear as changes since the latest recorded
  revision or checkpoint rather than being mislabeled as intentional revisions.

## Persistence Model

### `deck_revisions`

Add a table with:

- `id` UUID primary key;
- `deck_id` referencing the owning deck with cascade deletion;
- `title` required, 1-200 characters;
- `note` optional, up to 2,000 characters;
- `source` constrained to `selected_plans` or `single_plan`;
- `before_snapshot_id` referencing an internal revision snapshot;
- `after_snapshot_id` referencing an internal revision snapshot;
- `created_at` timestamp.

Both snapshot references use restrictive deletion semantics. Revisions cannot silently disappear
because an internal snapshot was deleted.

### `deck_revision_changes`

Add an immutable child table with:

- `revision_id` referencing the revision with cascade deletion;
- `card_id` referencing the card;
- frozen `card_name` for durable display;
- `direction` constrained to `addition` or `cut`;
- applied `quantity`;
- frozen `categories`, `added_by`, and `ai_reasoning` from the plan;
- optional `collection_id` with `ON DELETE SET NULL`;
- frozen `collection_name` so history remains readable if a collection is renamed or deleted;
- original `plan_created_at` and `plan_updated_at` timestamps;
- a uniqueness constraint on `(revision_id, card_id)`.

The revision records the selected plan's full pending quantity. A card cannot have simultaneous add
and cut plans because the existing plan model nets them into one row.

### Internal snapshots

Extend `deck_snapshots.source` with `revision`. Revision snapshots reuse the existing snapshot and
snapshot-card tables. They are excluded from ordinary snapshot listings and cannot be deleted via
the manual snapshot endpoint. Their labels identify whether they are the before or after side, but
the revision table is the authoritative relationship.

Revision snapshots preserve the same fields as existing snapshots. Freezing commander, partner,
description, planned changes, and prices remains outside this feature; the revision's immutable
change rows and before/after card compositions are the required historical record.

## Applying a Revision

Add an owner-scoped operation accepting:

- revision `title`;
- optional `note`;
- a non-empty list of unique selected `plan_ids`.

One database transaction performs these steps:

1. Lock the deck and selected plan rows.
2. Verify every selected plan belongs to the deck.
3. Validate collection ownership and sufficient inventory for selected additions.
4. Validate sufficient physical deck quantity for selected cuts.
5. Load and freeze card, collection, plan, and provenance details in memory.
6. Capture an internal before snapshot.
7. Apply every selected addition and cut using the existing collection-movement rules.
8. Capture an internal after snapshot.
9. Insert the revision and immutable change rows.
10. Delete only the selected plan rows.

Any failure rolls back snapshots, deck changes, collection movement, revision rows, and plan
consumption. Plans not included in `plan_ids` are never locked for mutation and remain pending.

The existing single-plan completion endpoint remains compatible but delegates to this operation with
one plan and a generated title such as `Added Sol Ring` or `Cut Arcane Signet`. The primary UI no
longer exposes card-by-card completion.

Direct deck-card endpoints continue to consume matching plan quantities as they do today. They do
not manufacture revisions because they lack a user-approved revision boundary. The History UI
surfaces those edits as differences from the newest revision or visible checkpoint.

## API

Add owner-scoped endpoints under `/api/v1`:

- `POST /decks/{deck_id}/revisions`
  - body: `title`, optional `note`, and `plan_ids`;
  - returns the complete created revision;
- `GET /decks/{deck_id}/revisions`
  - returns revision summaries newest first;
- `GET /revisions/{revision_id}`
  - returns revision metadata, change rows, and before/after snapshot summaries;
- `PATCH /revisions/{revision_id}`
  - changes only `title` and `note`.

Revision summaries include addition count, cut count, total added/cut quantities, resulting deck
card count, and before/after snapshot IDs. The existing comparison endpoint accepts those snapshot
IDs without a new diff implementation.

Validation errors use stable codes:

- `EMPTY_REVISION`;
- `DUPLICATE_PLAN_ID`;
- `PLAN_NOT_FOUND`;
- `INSUFFICIENT_DECK_QUANTITY`;
- `INSUFFICIENT_COLLECTION_QUANTITY`;
- `COLLECTION_NOT_OWNED`;
- `REVISION_NOT_FOUND`.

Error messages identify the affected card where that is safe for the authenticated owner.

## Planned Changes UI

Replace the per-row completion button with a checkbox. Add group-level selection controls for
additions and cuts plus a primary `Apply selected` action. Selection is local UI state and is reset
after a successful apply or when selected plans disappear after refresh.

`Apply selected` opens a confirmation dialog containing:

- required revision title with a useful date-based default;
- optional note;
- selected additions and cuts with quantities;
- collection movements;
- resulting projected deck size;
- clear confirmation that unselected plans remain pending.

The confirm action stays disabled until at least one plan is selected and the title is valid. While
submitting, selection and plan mutation controls are disabled. On failure the dialog remains open,
the selected plans remain selected, and the actionable server error appears beside the confirmation
controls.

Users may select only additions, only cuts, or any mixture. This explicitly supports applying newly
traded cards while leaving potential cuts open.

## History UI

The deck History tab becomes revision-first.

### Revisions

Display revisions newest first. Each summary shows:

- title and optional note;
- creation time;
- added and cut card/quantity counts;
- resulting physical deck size;
- manual or generated origin when relevant.

Expanding a revision shows immutable additions and cuts, quantities, collection movement, and
user/AI provenance. Actions link to:

- compare before snapshot with after snapshot;
- compare after snapshot with the current deck.

Title and note may be edited. Card changes, snapshot links, and timestamps cannot be changed.
Revisions are not deletable through the product UI.

### Checkpoints

Existing manual and automatic stage snapshots move into a secondary `Checkpoints` section. Manual
snapshot creation, deletion, and comparison remain available. Internal revision snapshots never
appear in this section.

### Changes since the latest record

The frontend chooses the newest baseline from the latest revision's after snapshot and visible
manual/automatic checkpoints. It compares that snapshot with the live deck using the existing
comparison endpoint. Added, removed, quantity-changed, or category-changed cards produce a concise
`Current deck has changes since the latest history entry` notice. The notice does not create or
modify history.

## Authorization and Failure Behavior

Every revision operation uses the existing account/deck ownership boundary. A revision from another
account returns the same not-found behavior used by snapshots. Selected collections must belong to
the current account.

Concurrent applies serialize on the deck and plan-row locks. A second request encountering consumed
plans fails without creating an empty revision. Internal snapshot creation is part of the same
transaction and is not best-effort.

## Verification

Backend tests cover:

- addition-only, cut-only, and mixed revisions;
- applying a selected subset while preserving unselected plans;
- multi-quantity plans;
- before and after reconstruction;
- collection inventory movement;
- insufficient inventory and physical quantity rollback;
- duplicate, missing, foreign-deck, and cross-account plan IDs;
- single-plan endpoint compatibility;
- internal snapshot filtering and deletion protection;
- revision title/note updates;
- concurrent or repeated application behavior.

Frontend tests cover:

- individual and group selection;
- addition-only application with cuts left pending;
- projected counts and confirmation contents;
- pending, success, and retained-error states;
- revision timeline expansion and metadata;
- before/after and current comparison links;
- checkpoint separation;
- the unrecorded-current-changes notice.

The implementation must pass backend Ruff, format, type checking, and pytest plus frontend lint,
typecheck, Vitest, and production build.

## Acceptance Criteria

1. Users can select any subset of planned additions and cuts and apply it as one named revision.
2. Applying a revision is atomic across deck cards, collection inventory, snapshots, revision rows,
   and plan consumption.
3. Unselected planned changes remain pending and unchanged.
4. Every revision preserves exact immutable changes and reconstructable before/after compositions.
5. History presents revisions as the primary timeline and existing snapshots as checkpoints.
6. Existing single-plan completion remains API-compatible and produces a one-card revision.
7. Direct unrecorded deck edits are visible as changes since the latest history entry.
8. Cross-account data is never exposed or mutated.

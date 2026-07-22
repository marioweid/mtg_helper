# Oracle Card Identity and Duplicate-Printing Repair

## Goal

Prevent different printings of the same Magic card from appearing as separate suggestions,
planned changes, or cards in a Commander deck. Repair existing active decks automatically while
preserving collection printing details and historical deck records.

Fellwar Stone is the motivating example: Scryfall exposes many printings with distinct Scryfall
IDs, but they all share one oracle ID and represent one Commander deck card.

## Root Cause

MTG Helper downloads Scryfall's `oracle_cards` bulk file, which contains one representative
printing for each oracle card at the time of the download. The representative printing can change
after a later release. The current sync upserts by `scryfall_id`, so the prior representative stays
in `cards` when a new representative arrives with the same `oracle_id`.

Several later boundaries compare printing-local identity:

- build-page suggestions and cross-stage state use `scryfall_id`;
- `deck_cards` is unique by `(deck_id, card_id)`;
- `deck_card_plans` is unique by `(deck_id, card_id)`;
- recommendation channels can resolve the same oracle card to different local rows.

Consequently, two rows with one oracle ID can pass through as different cards.

## Selected Approach

Use oracle identity end to end while retaining older card rows for compatibility. Exactly one row
per oracle ID is the canonical discovery row. Existing printing rows remain addressable by their
Scryfall IDs, but cannot be independently suggested or inserted into an active deck.

This approach is intentionally narrower than consolidating every foreign key in the database.
Collections intentionally record printing information, and snapshots and revisions are immutable
history. Neither should be destructively rewritten to solve an active-deck identity bug.

## Canonical Card Model

Add `cards.is_canonical BOOLEAN NOT NULL DEFAULT false`.

Create a partial unique index that permits at most one canonical row for each non-null oracle ID:

```sql
CREATE UNIQUE INDEX ... ON cards (oracle_id)
WHERE is_canonical AND oracle_id IS NOT NULL;
```

Cards without an oracle ID use their local card ID as their identity and are not constrained by
this index. Application code uses a single oracle key definition:

```text
oracle_key = oracle_id when present, otherwise local card id
```

An idempotent schema migration initializes existing rows before creating the index. It chooses one
deterministic representative per oracle ID, preferring the most recently released row and then a
stable UUID tiebreaker. The next successful Scryfall sync replaces that provisional choice with
the representative in the current bulk file.

Older rows remain queryable by exact local or Scryfall ID. Public search and discovery paths must
filter to canonical rows.

## Atomic Scryfall Sync

The canonical switch is part of the same database transaction as the card upserts:

1. Load the current Commander-relevant oracle-card representatives.
2. Upsert each current Scryfall row without making it canonical yet.
3. Mark all rows for the incoming oracle IDs non-canonical.
4. Mark the exact incoming Scryfall rows canonical.
5. Commit the upserts and canonical switch together.

The partial unique index guards step 4. External readers see either the previous complete canonical
set or the new complete set; they never see the intermediate switch. A failed download or upsert
leaves the prior canonical set unchanged.

New card rows default to non-canonical so a batch cannot violate the unique index before the switch.
Rows for cards absent from a particular filtered sync are not deleted.

## Identity Service

Introduce a focused card-identity service rather than duplicating oracle SQL throughout the
application. It provides these operations:

- resolve a local or Scryfall card ID to its oracle key;
- resolve any printing row to the current canonical row;
- bulk-map card IDs to canonical IDs;
- calculate the legal copy limit for a Commander deck card.

The service depends only on the cards table and Commander copy rules. Search, retrieval, deck,
planning, revision, import, swap, and collection-transfer services consume it.

## Discovery and API Behavior

The following card-discovery paths return canonical rows only:

- local card search;
- staged build retrieval and free-form suggestions;
- Top Picks;
- swaps, optimizer candidates, and mana suggestions;
- combo card resolution where a local card is required;
- Moxfield and Archidekt theme/source score resolution.

Recommendation scoring groups source evidence by oracle key. If legacy statistics reference
multiple rows for one oracle, the strongest score per source is mapped to the canonical row.

Add `oracle_id` to suggestion, deck-card, planned-change, and other card-summary response models
used by interactive deck building. Existing `CardResponse` already exposes it.

The frontend uses one helper:

```text
cardIdentity(card) = card.oracle_id ?? card.scryfall_id
```

Initial loads, load-more merges, buffers, rejected-card state, accepted-card state, and React keys
all use this identity. A different printing can therefore never survive as a second suggestion in
the same browser session.

## Write Guards

Every operation that changes an active deck resolves its incoming card to the canonical row before
reading or writing deck state:

- immediate card addition;
- planned addition or cut;
- revision application;
- swap application;
- list and URL import;
- moving a card from a collection into a deck.

Existing-deck and existing-plan checks compare oracle keys. Two Scryfall IDs for one oracle card
therefore target the same canonical deck row and plan. The server remains authoritative even if a
stale frontend submits an older printing ID.

Collection rows are not canonicalized. They retain their set code, collector number, foil flag,
condition, language, and purchase price. Collection ownership queries already group equivalent
printings by oracle key. When a collection copy is applied to a deck, its collection row remains
printing-specific while the active deck receives the canonical card row.

## Commander Copy Limits

Create one reusable copy-limit helper for both normal writes and repair.

- A normal Commander card has a maximum quantity of one.
- Basic lands have no application-level upper limit.
- Oracle text matching "A deck can have any number of cards named ..." has no application-level
  upper limit.
- Oracle text matching "A deck can have up to N cards named ..." uses the stated finite limit.
  The parser accepts numeric values and English number words from one through ninety-nine.

The helper never guesses from a card name. If a finite exception cannot be parsed, it falls back to
the safe singleton limit and logs the unrecognized text for review.

## Existing Active-Deck Repair

Run an idempotent repair after schema initialization at application startup. The repair examines
only groups with more than one local card row for the same `(deck_id, oracle_key)` and performs all
changes in one transaction.

For each active deck-card group:

1. Resolve the canonical card row.
2. Sum the quantities.
3. Clamp the sum to the card's legal copy limit; normal singleton cards become quantity one.
4. Union and stably sort all categories.
5. Preserve user-added provenance if any source row was user-added.
6. Preserve the first non-empty AI reasoning using deterministic row order.
7. Upsert one canonical deck row and remove the superseded active rows.

Commander and partner references on active decks are also resolved to canonical rows.

### Planned changes

Group plans by `(deck_id, oracle_key)`. Treat additions as positive quantities and cuts as negative
quantities, then sum them. Let `physical` be the repaired active quantity and `limit` the legal copy
limit. Clamp the projected quantity to the legal range and derive one normalized delta:

```text
projected = clamp(physical + signed_plan_total, 0, limit)
normalized_delta = projected - physical
```

For unlimited cards only the lower bound is applied. A zero delta deletes the redundant plans. A
positive delta becomes one canonical addition; a negative delta becomes one canonical cut.
Addition categories are unioned. Non-empty reasoning and user-added provenance are preserved using
the same deterministic policy as deck cards.

The repair does not modify collection cards, snapshots, snapshot cards, revisions, or revision
changes. Historical views resolve and group cards by oracle identity at read time without altering
the stored event.

Active deck reads also group by oracle identity and apply the same copy-limit and metadata rules.
This is normally a no-op after repair, but it prevents duplicate cards from reaching the UI if a
startup repair has rolled back and is waiting to retry.

## Preferences, Feedback, and Source Data

New preference and feedback writes resolve to canonical card rows. Existing rows remain valid:

- avoid and pet-card preferences apply when any row for the oracle carries that preference;
- per-deck feedback groups by oracle key; the row with the newest `created_at` supplies both the
  feedback state and its reject count, with card UUID as the deterministic tiebreaker;
- source statistics group by source plus oracle key and map their strongest score to the canonical
  card;
- ownership quantities continue to aggregate every printing in the selected collections.

This preserves useful historical signals without a risky foreign-key rewrite.

## Failure Handling and Observability

Before mutation, the repair calculates and logs:

- duplicate oracle groups in `cards`;
- affected active decks and planned changes;
- singleton quantities that will be removed;
- legal multi-copy quantities that will be merged.

The repair transaction rolls back completely on any unexpected conflict. The application logs the
exception and continues serving with canonical discovery, read-time grouping, and write guards.
Because the repair is idempotent and has no completion marker, it retries on the next startup.

Scryfall sync failure never changes canonical flags. Exact lookup of an older Scryfall ID continues
to work even when its row is non-canonical.

## Verification

Automated coverage should include:

- a later Scryfall sync choosing a new representative for an existing oracle ID;
- exactly one discoverable canonical card before and after the atomic switch;
- a failed sync retaining the prior canonical set;
- Fellwar Stone appearing once across stages, buffers, load-more calls, and source channels;
- server-side normalization when two submitted Scryfall IDs share one oracle ID;
- singleton repair retaining one copy;
- basic-land and explicit multi-copy exceptions retaining their merged legal quantities;
- opposing plans netting to one plan or zero;
- category, provenance, and reasoning preservation;
- repair idempotence;
- collections, snapshots, and revisions remaining unchanged;
- older exact Scryfall-ID lookups remaining available.

After deployment, a read-only audit groups active deck cards and plans by deck plus oracle key. It
must return no group with more than one card row. A second repair run must report zero mutations.

## Acceptance Criteria

- One oracle card appears at most once in any suggestion collection or active Commander deck.
- Different printings cannot create separate planned changes.
- Existing Fellwar Stone-like singleton duplicates are reduced to one active copy.
- Basics and cards with explicit multi-copy rules retain legal merged quantities.
- Scryfall sync cannot accumulate discoverable representative printings.
- Collections preserve exact printing metadata.
- Snapshots and revisions are not rewritten.
- A failed sync or repair cannot leave partially migrated active state.

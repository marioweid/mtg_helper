# Commander Top Picks

**Date:** 2026-07-22
**Status:** Approved design
**Scope:** Commander-specific Moxfield and Archidekt card-frequency recommendations

## Objective

Add a dedicated Top Picks tab to each deck. It shows cards commonly used with the deck's commander
across highly visible Moxfield and Archidekt Commander decks, exposes the source evidence, marks
cards already in the deck or planned, and lets users create planned additions directly.

The existing Moxfield commander signal already influences Build suggestions but is not independently
browsable. This feature exposes that evidence and adds equivalent, independently cached Archidekt
commander evidence without replacing theme, role, or Build-stage recommendations.

## Source Architecture

Moxfield and Archidekt remain independent ingestion adapters and caches. Source-specific failures,
sampling rules, and metadata do not leak into the other adapter.

### Moxfield

Reuse `moxfield_recs_service` and `moxfield_commander_recs`. It samples up to 10 of the most-liked
non-precon public decks for the exact commander, resolves printing IDs to oracle IDs, and records
how many sampled decks contain each card. Its existing 28-day cache age and Build-ranking behavior
remain unchanged.

### Archidekt

Add `archidekt_commander_recs_service` and `archidekt_commander_recs`. The adapter searches public
Commander decks containing the commander and orders candidates by views. Because an included-card
search can also return decks where the card is in the 99, every candidate deck is fetched and kept
only when its parsed commander list contains the exact commander name. Official or obvious raw
precon mirrors are excluded consistently with the intent of the Moxfield filter.

The adapter keeps up to 20 valid decks, records source deck IDs and view counts when available, and
aggregates one occurrence per card per deck. Card names are resolved case-insensitively to local
oracle-card rows. Unresolved names are skipped. The payload stores sampled deck metadata, per-card
counts, and enough diagnostic information to explain an empty sample.

Archidekt's public search exposes Commander format, included-card filtering, views, and view-based
ordering, but it does not expose the same likes model as Moxfield. The adapter therefore presents
views as its source-specific quality ordering rather than manufacturing likes.

Reference: <https://archidekt.com/search/decks>

### Caching and resilience

Archidekt uses the same initial 28-day maximum cache age as Moxfield. Missing or stale sources
refresh concurrently when Top Picks loads. Each adapter returns stale cached data on transient
upstream failure. A failure or empty result from one source never removes usable results from the
other source.

## Persistence

Add `archidekt_commander_recs`:

- `commander_id` UUID primary key referencing `cards(id)` with cascade deletion;
- `payload` JSONB containing source decks, card counts, sample size, and diagnostics;
- `fetched_at` timestamp.

Moxfield persistence is unchanged. Source payloads remain separate so they can evolve or be
invalidated independently.

## Normalized Top Picks

A `top_picks_service` converts both payloads to local card evidence and returns one list. Each pick
contains:

- standard card identity and display fields, including image, mana cost, type line, and EUR price;
- Moxfield inclusion count, sample size, and rate;
- Archidekt inclusion count, sample size, and rate;
- combined score;
- current physical deck quantity;
- planned addition or cut quantity;
- collection ownership.

Commander and partner cards are excluded. Cards outside the commander's color identity are also
excluded defensively.

The combined score weights both available sources equally and adds a small bounded consensus bonus
when the card appears in both. When only one source produced a usable sample, that source is
reweighted to the full base score rather than penalizing every result. Ordering is combined score,
then number of supporting sources, then aggregate inclusion count, then card name. Raw counts and
sample sizes remain visible so the ranking is auditable.

## API

Add an owner-scoped endpoint:

- `GET /api/v1/decks/{deck_id}/top-picks`
  - optional `source=combined|moxfield|archidekt`, default `combined`;
  - returns source summaries and normalized picks in `DataResponse`;
  - missing or foreign decks use the existing not-found behavior.

The response includes, for each source, sample size, fetched timestamp, stale-cache status, and an
optional safe error message. A total source failure returns an empty successful response with both
source diagnostics so the UI can explain the problem and retry. Unexpected internal errors retain
the standard error envelope.

Planning uses the existing `POST /decks/{deck_id}/planned-changes` endpoint with direction
`addition`, quantity one, and user provenance. The Top Picks endpoint never mutates the deck or
plans.

## Top Picks Tab

Add `top-picks` beside Cards, Combos, and History on the deck page. Loading is lazy: the endpoint is
called only after the tab is opened.

The tab renders:

- source summaries with sample sizes, cache timestamps, and isolated errors;
- Combined, Moxfield, and Archidekt source filters;
- card-name search;
- a Hide cards already in deck toggle;
- a responsive card grid ordered by the active source score.

Each card shows its image and existing hover preview, mana/type/price context, collection ownership,
combined usage, and evidence badges such as `Moxfield 8/10` and `Archidekt 14/20`.

Card state and actions are explicit:

- physical copies show `In deck` with quantity;
- pending additions show `Already planned` with quantity;
- pending cuts show `Cut planned` and do not silently offset the cut;
- otherwise `Plan addition` creates a one-copy planned addition and refreshes deck and Top Picks
  state.

The tab includes all common cards by default, including cards already present, so it works as both
a commander reference and an upgrade finder. It never automatically adds or applies a card.

## Empty and Failure States

- One healthy source: show its picks and the other source's diagnostic.
- Stale cache after refresh failure: show stale picks and label the source stale.
- No cached or fresh data: show an explanatory empty state and a Retry action.
- A planning conflict or API error: keep the current list and show the existing actionable error.
- Search/filter with no matches: show a local empty-filter message without refetching.

## Verification

No new tests are added, following the user's earlier preference. Verification consists of targeted
backend Ruff checks and import/route checks, frontend typecheck and lint, the existing frontend test
suite, and a production build. Database-backed integration tests may remain unavailable when local
PostgreSQL is stopped and must be reported explicitly.

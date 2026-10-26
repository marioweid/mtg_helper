# New Cards — Scryfall tag-matching contract

New Cards returns deterministic source-tag matches, not generated advice. No AI worker,
analysis queue, budget, daily run, or worker-permission setting is used.

## HTTP contract

All routes require the current account and deck ownership. Base `/api/v1/decks/{deck_id}`.
All successful responses use the existing `{data: ...}` envelope.

- `GET /new-cards` reads current matches without starting model work or source refresh.
- `POST /new-cards/{oracle_id}/dismiss` hides a match in this deck only.
- `DELETE /new-cards/{oracle_id}/dismiss` undoes a dismissal.
- `POST /new-cards/{oracle_id}/plan` idempotently plans one addition after rechecking eligibility
  under the deck lock. It does not edit the physical deck or plan supporting swaps.

Each action returns `NewCardsResponse`. There are no New Cards admin-analysis endpoints.
Existing Admin Scryfall sync publishes the card and Oracle-tag inputs together.

```ts
interface NewCardsResponse {
  status: "ready" | "unavailable" | "source_stale" | "source_mismatched";
  catalog_updated_at: string | null;
  tag_updated_at: string | null;
  stale: boolean;
  eligible_count: number;
  dismissed_count: number;
  error: string | null;
  matches: NewCardMatch[];
}

interface TagMatch {
  commander_tag_id: string;
  commander_tag_label: string;
  candidate_tag_id: string;
  candidate_tag_label: string;
  relation: "direct" | "descendant";
}
```

`NewCardMatch` includes Oracle, internal-card and printing identities; source facts; `image_uri`;
`scryfall_uri`; release and expiry dates; optional EUR price; `matching_tag_count`; and `tag_matches`.
The backend models in `backend/src/mtg_helper/models/new_cards.py` define the full response.

## Matching and source boundaries

- Match the Commander and optional partner only, never deck strategy or other deck contents.
- Union their directly assigned Oracle-tags. A candidate must have the identical tag or one of
  its descendants directly assigned. Count each matching Commander tag once.
- Preserve the 60-UTC-day window, Commander legality, paper-release filters, and color identity.
  Previews, reprints of older cards, unknown origins, and promo-only originals are not eligible.
- Rank by matching-tag count descending, release date descending, then stable name/Oracle identity.
- Hide physical cards, planned additions, and dismissals only for the current deck.
- Missing Commander or partner tags, stale inputs, and mismatched source generations are source
  problems, not complete no-match results. A new request reads the current published sources.
- A shared source tag is not proof of synergy, rules interaction, or suitability for the deck.

## Presentation and planning

Cards use the shared artwork-first grid. Their printed rules are not duplicated below the image.
Small tag chips expose the exact source relationship on hover, focus, or tap; Escape closes the
explanation. Missing artwork retains the card name, source link, and explicit deck actions.

Pilot-origin planned additions retain transactional legality, color and copy validation on physical
completion. Age expiry alone does not invalidate a saved plan. No action automatically changes the
physical deck.

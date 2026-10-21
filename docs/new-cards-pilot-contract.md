# Experimental New Cards pilot — implementation contract

User approved implementation and explicitly chose **released, Commander-legal cards first**.
Previews, unknown-release products, and promo-only originals are excluded and disclosed, not
asserted future-legal. The pilot does not implement preview discovery.
No automatic physical deck changes. Model output is advisory and labeled unverified.

## HTTP contract

All routes require the current account and deck ownership. Base `/api/v1/decks/{deck_id}`.
All successful responses below use the existing `{data: ...}` envelope.

- `GET /new-cards` → `NewCardsResponse`. Read-only; never starts AI or catalog sync.
- `POST /new-cards/{oracle_id}/dismiss` → `NewCardsResponse`.
- `DELETE /new-cards/{oracle_id}/dismiss` → `NewCardsResponse` (undo).
- `POST /new-cards/{oracle_id}/plan` → `NewCardsResponse`. Plan one addition only, idempotently;
  recheck live eligibility under the deck lock. No auto-completion, no supporting swaps.

`NewCardsResponse`:

```ts
interface NewCardsResponse {
  status: "unavailable" | "idle" | "waiting" | "running" | "daily_limit" | "error";
  catalog_updated_at: string | null;
  analyzed_at: string | null;
  stale: boolean;
  eligible_count: number;
  assessed_count: number;
  remaining_count: number;
  dismissed_count: number;
  error: string | null;
  picks: NewCardPick[];
}
interface NewCardFace {
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string;
  power: string | null;
  toughness: string | null;
}
interface NewCardPick {
  oracle_id: string;
  card_id: string;
  scryfall_id: string;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string;
  power: string | null;
  toughness: string | null;
  faces: NewCardFace[];
  image_uri: string | null;
  scryfall_uri: string;
  released_at: string;
  expires_at: string;
  price_eur_cents: number | null;
  label: "strong" | "worth_testing";
  reason: string;
  caveat: string;
  required_changes: string[];
  evidence: { name: string; quote: string }[];
}
```

GET only reads the shared Commander-Konstellation result; it never starts model work. Candidates and
cache identity use Commander Oracle IDs/facts, card facts, release date and evaluator version — never
deck content, account identity, strategy, plans, preferences, goals, bracket or memory. Dismissal and
planning remain deck-local. Coverage refers to the current shared candidate pool; rejects count as
assessed, but incomplete or stale work never publishes picks or a no-match result.

Global admin routes are `GET`/`PUT /api/v1/admin/new-cards`, `POST /admin/new-cards/start`, and
`POST /admin/new-cards/cancel`. They require both admin authorization and the process-level
`ENABLE_NEW_CARDS_WORKER=true` opt-in; Compose explicitly keeps this disabled. The global daily limit
defaults to 100 packages and is charged before a provider call.

## Pilot boundaries

- Shared discovery integrates atomically into Scryfall sync; full printing history establishes
  earliest regular eligible paper release, not representative printing dates or early promos.
- Conservative normal-product allowlist plus unknown historical-origin exclusions; no claim of
  complete preview/special-product coverage. Daily production refresh; Admin sync for bootstrap.
- No external community scraping, new dependencies, or broad changes to manual/Rule 0 behavior.
- Pilot-origin planned additions receive transactional legality/color/copy revalidation at both
  single and batch physical completion. Age expiry alone does not invalidate a saved plan.
- Test through a feature branch and PR, not a direct main push. No deployment or live model call
  is needed to verify the implementation locally; production sync occurs only after deployment.

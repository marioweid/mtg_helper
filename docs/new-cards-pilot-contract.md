# Experimental New Cards pilot — implementation contract

User approved implementation and explicitly chose **released, Commander-legal cards first**.
Previews, unknown-release products, and promo-only originals are excluded and disclosed, not
asserted future-legal. This supersedes the broader draft's preview scope for the pilot only.
No automatic physical deck changes. Model output is advisory and labeled unverified.

## HTTP contract

All routes require the current account and deck ownership. Base `/api/v1/decks/{deck_id}`.
All successful responses below use the existing `{data: ...}` envelope.

- `GET /new-cards` → `NewCardsResponse`. Read-only; never starts AI or catalog sync.
- `POST /new-cards/analyze` → `NewCardsResponse` (202). Explicitly assess next eight unassessed
  eligible cards in background. One active analysis per account across workers, durable PostgreSQL
  lease, bounded timeout/tokens, no retries, daily account quota. Repeated clicks share current work.
- `POST /new-cards/{oracle_id}/dismiss` → `NewCardsResponse`.
- `DELETE /new-cards/{oracle_id}/dismiss` → `NewCardsResponse` (undo).
- `POST /new-cards/{oracle_id}/plan` → `NewCardsResponse`. Plan one addition only, idempotently;
  recheck live eligibility under the deck lock. No auto-completion, no supporting swaps.

`NewCardsResponse`:

```ts
interface NewCardsResponse {
  status: "unavailable" | "idle" | "running" | "error";
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

GET filters expired, in-deck, pending-addition, dismissed, avoided and illegal cards on every read.
Coverage refers to the currently eligible pool; rejects count as assessed. No minimum suggestion
count. Incomplete coverage must not look like a completed empty result. Old-context assessments are
not displayed as current. Support facts use physical cards only; pending cuts are included as warnings.

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

# Suggested Mana Curve Design

## Goal

Add an always-visible recommended mana curve for Commander decks so users can compare their current curve against a target while viewing a deck, comparing decks, and building a deck.

## Scope

Version 1 provides a conservative hybrid recommendation:

- Prefer commander-specific curve data from Moxfield top decks.
- Use a generic Commander fallback when there are fewer than 5 usable Moxfield decks.
- Do not use EDHREC to shape the curve in v1.
- Exclude commander, partner, and lands from both current and recommended curve counts.
- Use buckets `0, 1, 2, 3, 4, 5, 6, 7+`.

## Data Source and Aggregation

The existing Moxfield recommendation pipeline already fetches top-liked non-precon decks for each commander. Extend that pipeline to collect mana-value data from each fetched deck's mainboard.

For each successfully fetched Moxfield deck:

1. Read mainboard cards only.
2. Exclude lands.
3. Bucket each non-land card by CMC into `0..6` or `7+`.
4. Count one per listed mainboard card. Commander and partner zones remain excluded.

If at least 5 decks produce curve data, average each bucket across those decks and store the result as commander-specific. If fewer than 5 decks produce curve data, store or return the generic fallback recommendation instead.

EDHREC remains used for card recommendation/inclusion signals only. It is not a full decklist source and should not influence mana curve targets in v1.

## Backend/API Design

Extend the cached `moxfield_commander_recs.payload` shape with curve metadata, for example:

```json
{
  "moxfield_card_id": "...",
  "decks": [],
  "by_oracle": {},
  "curve": {
    "source": "moxfield",
    "deck_count": 8,
    "confidence": "high",
    "buckets": { "0": 1, "1": 7, "2": 13, "3": 12, "4": 9, "5": 6, "6": 3, "7+": 2 }
  }
}
```

Add Pydantic models for the API surface, such as:

- `ManaCurveBuckets`
- `ManaCurveRecommendation`
- `ManaCurveDelta`
- `DeckManaCurve`

Expose curve data on:

- `DeckDetailResponse` for deck overview and build pages.
- `DeckCompareResponse` for comparison pages.

A helper/service should handle:

- Current deck curve calculation from deck cards.
- Recommended curve lookup from cached Moxfield payload.
- Generic fallback selection.
- Full-deck deltas.
- Progress-aware deltas for partially built decks.

Avoid a separate endpoint in v1 because deck overview/build/compare already fetch deck-shaped responses.

## Frontend Design

Upgrade `ManaCurve` to accept current and recommended curve data.

Deck overview:

- Show current curve bars with recommended markers or overlays.
- Show a short actionable summary, e.g. `Needs +3 at MV 2, +1 at MV 3; high at MV 5+`.
- Show source metadata: `Based on 8 Moxfield decks` or `Generic Commander fallback`.

Build flow:

- Add a compact always-visible curve guide near the existing deck/build status UI.
- Use progress-aware deltas so the user sees which mana values to prioritize while the deck is incomplete.

Deck comparison:

- Show each side's current curve against its recommendation.
- If both sides share a commander, both sides naturally use the same recommendation.
- If commanders differ, each side uses its own commander-specific or fallback recommendation.

## Error Handling

Moxfield errors must remain non-fatal:

- Transient Moxfield failures return existing cached payload when available.
- Sentinel/empty payloads return generic fallback curve.
- Missing or malformed curve data returns generic fallback curve.
- The UI always receives a recommendation and can always render the comparison.

## Testing Plan

Backend tests:

- Moxfield payload aggregation still computes `by_oracle` correctly.
- Moxfield payload aggregation computes `curve` correctly.
- Lands are ignored in curve buckets.
- Commander/partner zones remain excluded.
- At least 5 usable decks are required for `source = "moxfield"`.
- Fewer than 5 usable decks produces `source = "fallback"`.
- Deck detail response includes curve recommendation.
- Deck comparison response includes curve recommendation for both sides.

Frontend tests or component checks:

- `ManaCurve` renders current bars and recommendation markers.
- Source label renders Moxfield vs fallback text.
- Delta summary highlights shortage and surplus buckets.

## Out of Scope for v1

- EDHREC-derived curve targets.
- Archetype/tag-adjusted curve targets.
- User-customizable target curves.
- New persistent table for curve recommendations.
- Recommendation-driven automatic card replacement.

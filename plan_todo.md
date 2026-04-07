# Plan: Add Manual Card Search + Prompt Suggestions to Build Page

## Context

The build wizard page (`frontend/app/decks/[id]/build/page.tsx`) generates AI suggestions per stage but has no way to:
1. **Manually search and add cards** — users can't type a card name and add it directly
2. **Get prompt-based suggestions** — users can't override the stage query with a custom prompt (e.g. "token doublers" instead of the deck description's "+1/+1 counters")

The load more button already exists (lines 502-518).

## Feature 1: Manual Card Search Bar

A search input that uses the existing `apiClient.searchCards()` endpoint with fuzzy matching and commander color identity pre-filtering.

### Changes to `frontend/app/decks/[id]/build/page.tsx`

**New state** (via `useState`, not the reducer — independent of stage state):
- `deckDetail: DeckDetailResponse | null` — fetched on mount for color identity
- `searchQuery: string` — search input value
- `searchResults: CardResponse[]` — results from `searchCards`
- `searchLoading: boolean`
- `searchOpen: boolean` — toggle to show/hide search section

**On mount:** Fetch deck detail via `apiClient.getDeck(deckId)` to get `commander_id`, then `apiClient.getCard(commander_scryfall_id)` — actually the deck detail doesn't include commander's color identity directly. Check `DeckDetailResponse.cards` for the commander, or fetch the card.

Simpler: use `searchCards` with `color_identity` filter derived from the deck's cards (already computed on the detail page via `colorIdentityFromCards`). Or: fetch the deck detail and compute color identity from the commander card.

Actually even simpler: `searchCards` has a `commander_legal: true` filter but the `color_identity` param is a string like `"W,U,B"`. The build page already has access to `deckId` — fetch the deck once to get its cards and derive color identity.

**UI placement:** Below the target stepper, above the suggestions grid. A collapsible section:

```
[🔍 Search cards...]  [toggle button]
```

When open:
- Text input with debounced search (300ms)
- Results shown as a compact list (not the full CardSuggestionCard — simpler since these are `CardResponse`, not `CardSuggestion`)
- Each result: card image thumbnail, name, mana cost, type line, "Add" button
- Clicking "Add" calls `apiClient.addCard(deckId, { card_scryfall_id, category: activeStage, added_by: "user" })`
- After adding, the card is removed from search results (or marked as added)
- Pre-filters: `commander_legal: true`, `color_identity` from deck's commander

### New component: `frontend/components/card-search-result.tsx`

Small component for rendering a search result row:
- Props: `card: CardResponse`, `onAdd: () => void`, `added: boolean`
- Shows: name, mana cost, type line, image (small), Add/Added button

## Feature 2: Prompt-Based Suggestions

A text input where the user types a custom prompt (e.g. "token doublers") and gets AI suggestions back, independent of the current stage query.

### Changes to `frontend/app/decks/[id]/build/page.tsx`

**New state:**
- `promptInput: string` — input value
- `promptSuggestions: CardSuggestion[]` — results from suggest API
- `promptStatuses: Record<string, SuggestionStatus>` — accept/reject tracking
- `promptLoading: boolean`
- `promptOpen: boolean` — toggle visibility
- `promptQuantities: Record<string, number>` — for basic land quantity control

**Submit handler:** Calls `apiClient.suggestCards(deckId, promptInput, 10)` and displays results.

**Clear/close:** Closing the prompt section or clearing the input resets `promptSuggestions` to `[]`.

**UI placement:** Below the search bar, above the stage suggestions. Another collapsible section:

```
[💬 Suggest cards...]  [toggle button]
```

When open:
- Text input + submit button
- Results displayed using the same `CardSuggestionCard` component (they're `CardSuggestion` type)
- Accept/reject works the same as stage suggestions: `apiClient.addCard()` / `apiClient.addFeedback()`
- Section clearly labeled "Custom Suggestions" to distinguish from stage suggestions below

**Accept/reject handlers:** Same as the stage handlers but using `promptStatuses` and `promptQuantities` state. I'll reuse the existing `handleAccept` logic but extract it to work with both state sources.

## Files to Modify/Create

1. **`frontend/app/decks/[id]/build/page.tsx`** — add search + prompt sections, fetch deck detail on mount, new state variables, handlers
2. **`frontend/components/card-search-result.tsx`** (new) — compact card display for search results
3. **`frontend/lib/types.ts`** — no changes needed (CardResponse and CardSuggestion already exist)
4. **`frontend/lib/api.ts`** — no changes needed (searchCards and suggestCards already exist)

## Verification

1. `PATH="/usr/local/Cellar/node/25.8.2/bin:$PATH" pnpm exec tsc --noEmit` — no type errors
2. Open build page → search bar visible → type card name → results appear filtered by color identity
3. Click "Add" on a search result → card added to deck
4. Open prompt section → type "token doublers" → AI suggestions appear
5. Accept/reject prompt suggestions → works like stage suggestions
6. Stage suggestions still work independently below

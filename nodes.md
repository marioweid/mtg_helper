# Plan: Add "Bangers" Stage to Build Wizard

## Context

Users with existing decks (e.g., precons) want to upgrade by swapping out ~10 cards. After removing weak cards from their decklist, they need a way to see the **best possible additions across all categories** — not just ramp or draw, but the highest-scoring cards for the deck regardless of category. This is the "Bangers" tab: a cross-category view of top picks.

## Design

- **UI placement:** First tab in the build wizard stage bar, before Ramp
- **Backend:** Broad single retrieval using deck description + all category tags combined
- **Not a real stage:** Bangers doesn't participate in auto-advance or stage tracking — it's a static utility tab

## Files to modify

### Backend

#### 1. `backend/src/mtg_helper/services/retrieval_service.py` — stage query mapping

Add bangers entry to `_STAGE_QUERIES` (line 178):

```python
"bangers": (
    "powerful staples synergy commander",
    [
        "ramp", "fast_mana", "draw", "removal", "counterspell",
        "board_wipe", "protection", "tutor", "graveyard", "blink",
        "token", "sacrifice", "aristocrats",
    ],
),
```

This gives broad tag coverage across all categories. The deck description gets appended by `stage_retrieval_query()` (line 559-564) for semantic relevance.

Lands are excluded automatically because stage ≠ "lands" (handled by existing `_search_tags` filter).

#### 2. `backend/src/mtg_helper/services/ai_service.py`

**`_resolve_stage()`** (line 437): Add `"bangers"` to the active stages whitelist so the API accepts it as a valid explicit stage. Currently uses `[s for s in STAGES if s != "complete"]` — change to include bangers:

```python
active_stages = [s for s in STAGES if s != "complete"] + ["bangers"]
```

Since bangers is always explicitly requested (never auto-advanced), `advance_deck_stage` is already False.

**`_STAGE_META`** (line 39): Add entry for bangers:

```python
"bangers": ("bangers", "top picks across all categories"),
```

#### 3. `backend/src/mtg_helper/services/deck_service.py` — NO changes

`STAGES` list stays unchanged. Bangers is not a progression stage — the deck's `stage` column never holds "bangers". Auto-advance (created → ramp → ... → complete) is unaffected.

### Frontend

#### 4. `frontend/lib/constants.ts`

```typescript
// CATEGORY_ORDER: add "bangers" at position 0
export const CATEGORY_ORDER = ["bangers", "ramp", "interaction", "draw", "theme", "utility", "lands"];

// STAGE_LABELS: add entry
bangers: "Bangers",

// CATEGORY_TARGETS: generous range since it's cross-category
bangers: [10, 15],

// STAGE_DEFAULTS: default target
bangers: 10,
```

`STAGES` (the progression list with "complete") stays unchanged.

#### 5. `frontend/app/decks/[id]/build/page.tsx`

No structural changes needed — the stage tab bar iterates `CATEGORY_ORDER`, and the wizard reducer initializes state from it. Bangers will appear as the first tab automatically and use the same `buildStage()` API call with `stage: "bangers"`.

Optional visual distinction (e.g., star icon or accent color on the tab) can be deferred.

## Verification

- `cd backend && uv run pytest -q` — all tests pass
- `uv run ruff check . && uv run ruff format .`
- Frontend: `PATH="..." pnpm exec tsc --noEmit && pnpm build`
- Manual test: open build wizard → Bangers is first tab → load suggestions → cards span multiple categories
- Verify auto-advance still works: building via auto-advance skips bangers, goes ramp → interaction → ...

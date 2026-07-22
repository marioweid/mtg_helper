# History Card Hover and Keyword Browser

**Date:** 2026-07-22
**Status:** Approved design
**Scope:** Revision card previews and deck keyword navigation

## Objective

Show the exact card image when a user hovers or taps a card recorded in deck revision history, and
replace the keyword editor's long vertical group catalog with searchable, one-group-at-a-time
navigation. Keyword selection and persistence semantics remain unchanged.

## Revision Card Preview

`DeckRevisionChange` gains an optional `image_uri`. The revision service obtains it by joining each
immutable change's stored `card_id` to the current `cards` row while hydrating revision responses.
The revision record continues to freeze the card name and other change metadata; the image URL is a
rendering aid rather than historical state.

The History view wraps each expanded revision card name in the existing `CardHover` component and
passes both `card_name` and `image_uri`. This uses the established delayed desktop hover and touch
preview behavior without adding another preview implementation. If an image URL is missing or no
longer works, `CardHover` retains its existing lazy-resolution and unavailable-image behavior.

## Searchable Keyword Browser

The `ArchetypeChipPicker` keeps the Selected section at the top so current choices are always
visible and removable. The theme and advanced-mechanic catalogs are normalized into one ordered
list of selectable groups. Advanced mechanic groups retain an explicit label prefix so their
source remains clear.

Below Selected, the picker renders:

1. one search input matching group display names and individual keyword labels;
2. one compact top-level group selector containing only groups that match the current search;
3. one keyword-chip panel for the active group.

Only the active group's chips are rendered. Searching for a group name keeps all of that group's
chips visible. Searching for a keyword keeps its containing group available and visually
highlights matching chips. If the active group is absent from filtered results, the first matching
group becomes active. Clearing the search restores the complete group selector without changing
selected keywords. When no groups match, the picker shows an explicit empty result.

The selector shows each group's display name and selected/total keyword counts to make populated
groups easy to recognize. Loading and API error behavior remain as they are today. The picker API,
deck update request, keyword tags, suggested states, and selection order do not change.

## Accessibility and Responsive Behavior

The search input and group selector have visible labels. Keyboard users can search, choose a group,
and toggle chips using native controls. The single active panel uses the same layout on desktop and
mobile, avoiding horizontal tab overflow and long page scrolling.

## Failure Behavior

Missing card images degrade through the existing `CardHover` fallback. Keyword catalog loading
failures continue to show the current inline error. Search and active-group state are local UI state
and never alter the deck until the existing Save keywords action succeeds.

## Verification

No new tests are added, following the user's earlier preference. Verification consists of targeted
backend Ruff checks and route/model import checks plus frontend typecheck, lint, the existing test
suite, and a production build.

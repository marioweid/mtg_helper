# History Card Hover and Keyword Browser

**Date:** 2026-07-22
**Status:** Approved design
**Scope:** Revision card previews and deck keyword navigation

## Objective

Show the exact card image when a user hovers or taps a card recorded in deck revision history, and
replace the keyword editor's long vertical group catalog with searchable direct theme chips,
ungrouped themes, and collapsible official keyword categories. Keyword selection and persistence
semantics remain unchanged.

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
visible and removable. It then renders one global search field followed by three semantic tiers:

1. **Theme groups:** every active group created in the admin panel is already represented by one
   stable selectable slug, so these groups render directly as toggle chips without another
   navigation layer;
2. **Ungrouped themes:** enabled Moxfield and Archidekt tags without an admin group render together
   as an always-visible chip cloud below the admin-defined groups;
3. **Official keywords:** MTGJSON ability words, keyword abilities, and keyword actions retain their
   category headings and render in collapsible sections.

The global search matches display labels and stored tag values across all three tiers. It filters
chips inside each section while preserving tier order and highlights matches. Sections with no
matches disappear during search; when nothing matches, the picker shows one explicit empty result.
Clearing search restores the full catalog without changing selected keywords.

Official keyword categories are collapsed by default. A category opens automatically when it
contains a selected keyword or a search match, and users may otherwise open or close categories
independently. Admin-defined groups and ungrouped themes remain directly visible because they are
the primary deck-theme choices.

Selected, suggested, and search-matching chips retain distinct styling. Loading and API error
behavior remain as they are today. The picker API, deck update request, keyword tags, suggested
states, selection order, admin data, and persistence do not change.

## Accessibility and Responsive Behavior

The search input and section controls have visible labels. Keyboard users can search, expand
official categories, and toggle chips using native controls. Wrapping chip clouds use the same
layout on desktop and mobile, while collapsed official categories prevent excessive initial
scrolling.

## Failure Behavior

Missing card images degrade through the existing `CardHover` fallback. Keyword catalog loading
failures continue to show the current inline error. Search and active-group state are local UI state
and never alter the deck until the existing Save keywords action succeeds.

## Verification

No new tests are added, following the user's earlier preference. Verification consists of targeted
backend Ruff checks and route/model import checks plus frontend typecheck, lint, the existing test
suite, and a production build.

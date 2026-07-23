# Collapsible Deck Groups Design

**Date:** 2026-07-23

## Goal

Allow every grouped section in the deck view to be expanded or collapsed in both Grid and List
views while keeping all card groups expanded by default. Planned additions and cuts remain the only
deck-page section that starts collapsed.

## Interaction

Every primary-type and tag-group header becomes an accessible toggle. The header continues to show
the group label and card count and adds a chevron that communicates the current state.

- Clicking the header expands or collapses its cards.
- All groups start expanded when the deck page opens.
- Collapsed choices remain consistent when switching between Grid and List during the current page
  visit.
- Collapsed choices are not stored in local storage or sent to the server.
- Reopening or reloading the deck resets every card group to expanded.
- Filtering and sorting do not reset the temporary state of groups that remain on the page.

## Component design

`DeckDetailPage` owns a temporary set of collapsed group keys. Keys include the grouping mode and
group identifier so type and tag groups cannot affect each other accidentally.

The page passes the collapsed set and a toggle callback to both `DeckGrid` and
`DeckCompactColumns`. Each component:

1. Determines whether a rendered group is collapsed.
2. Renders its header as a button with `aria-expanded` and an associated content identifier.
3. Omits the card grid or compact list while the group is collapsed.

No API, database, or browser-storage changes are required. The existing collapsed-by-default
behavior of `PlannedChangesPanel` is unchanged.

## Accessibility

- Group toggles are real buttons and work with keyboard activation.
- Each button exposes `aria-expanded` and `aria-controls`.
- The group count remains visible while collapsed.
- The chevron is decorative and hidden from assistive technology.

## Validation

Frontend lint, TypeScript checking, and the production build will validate the implementation.
Per the established request, no tests will be added or run.

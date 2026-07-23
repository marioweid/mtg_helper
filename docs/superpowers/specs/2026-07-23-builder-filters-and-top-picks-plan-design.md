# Builder Filters and Top Picks Planning Design

**Date:** 2026-07-23

## Goal

Reduce builder-page scrolling by consolidating all suggestion filters into one compact dropdown,
start planned changes collapsed, and prevent Top Picks planning from collapsing the result grid or
resetting the user's scroll position.

## Builder filter dropdown

Replace the separate collection, price, card-type, and subtype panels with one `Filters` button and
anchored dropdown.

The dropdown contains:

1. An owned-cards control with the existing collection selector. Users can choose the collections
   used for suggestion ownership filtering.
2. Minimum and maximum EUR price fields with the existing apply and clear behavior.
3. All existing primary card-type filters.
4. All existing subtype filters.

The trigger displays the number of active filters. The dropdown also provides a single `Clear all`
action. It stays open while filters are selected and closes through its close control, Escape, or a
click outside. Existing filter semantics remain unchanged: collection and type selections apply
immediately, while price text fields apply through their existing action.

The collection selection remains persisted through the deck's
`suggestion_collection_ids`. Price, type, and subtype filters retain their current scope and
suggestion-refresh behavior.

## Planned changes

The builder's Planned Changes section uses a collapsed `<details>` state on initial render,
regardless of whether plans exist. Its summary continues to show the useful counts so users can see
that changes exist without opening the section.

## Top Picks planning

The current planning flow reloads Top Picks with its blocking loading state. That temporarily
replaces the result grid with a short loading message, collapses the document height, and moves the
browser's scroll position.

After a successful `Plan addition` request:

- Update the selected Top Pick locally to show it as planned.
- Refresh the parent deck data in the background so Planned Changes and deck counts stay current.
- Do not enter the blocking Top Picks loading state, refresh the route, or replace the result grid.
- Keep the action button as `type="button"` and disable only the card being submitted.
- Preserve existing error handling. If planning fails, leave the card unchanged and show the error.

The normal blocking loading state remains appropriate for the initial Top Picks load and explicit
source changes.

## Accessibility and responsive behavior

- The Filters trigger exposes its expanded state and controls relationship.
- Keyboard users can close the dropdown with Escape.
- The dropdown is anchored on wider layouts and constrained to the viewport on smaller screens.
- Existing labeled inputs and checkbox controls remain keyboard accessible.

## Scope

This change is frontend-only. It does not alter API contracts, database schema, or server-side
filter behavior. Per the user's request, implementation validation will use lint/type/build checks
without adding or running tests.

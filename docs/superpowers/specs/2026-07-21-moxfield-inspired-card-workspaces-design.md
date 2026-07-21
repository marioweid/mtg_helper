# Moxfield-Inspired Card Workspaces

**Date:** 2026-07-21
**Status:** Approved design
**Scope:** Deck detail, collection detail, and the builder's expandable deck surface

## Objective

Make deck and collection browsing clearer, more visual, and more consistent by adopting familiar
interaction patterns from Moxfield without copying its interface. MTG Helper keeps its dark indigo
identity, refined with neutral charcoal surfaces and stronger contrast.

The first-use default is a visual card grid. Users can switch to a compact list and the application
remembers their choice. The builder's current full-width expanded bar becomes a right-side drawer
on desktop and a near-full-screen bottom sheet on mobile.

## Design Principles

- Cards are the primary content; analytics and secondary actions should not compete with them.
- Decks, collections, and the builder use the same vocabulary for search, filters, sort, grouping,
  view selection, card tiles, loading, and empty states.
- Common actions remain discoverable without covering every card with controls.
- Existing capabilities and data models are preserved.
- Responsive behavior is deliberate rather than a compressed desktop layout.
- Moxfield is an interaction reference, not a visual template.

## Shared Workspace Structure

Deck and collection detail pages use the same high-level structure:

1. A compact page header contains the title, item count, important metadata, and primary actions.
2. A sticky workspace toolbar contains search, active filters, grouping, sorting, result count, and
   a labeled Grid/List switcher.
3. The card workspace fills the main content area and owns loading, empty, no-results, and local
   error states so the surrounding page does not jump.
4. Grid is the first-use default. The most recently selected view, sort, and grouping preferences
   are restored on later visits.
5. Card selection opens the existing detail experience. Frequently used mutations are available
   from the tile or its compact action menu; secondary actions remain in card details.

Card tiles prioritize artwork recognition and expose quantity and relevant status badges at all
times. Badges use text or icons as well as color. Tile density is responsive: more columns on wide
screens, fewer on narrow screens, with artwork remaining legible.

## Deck Detail Page

The deck page retains all current capabilities: commander and partner display, description,
archetype tags, bracket and stage metadata, build navigation, card search, tag/type grouping,
sorting, filtering, quantity changes, removal, combos, history, planned changes, statistics, mana
curve, scorecard, mana assistance, and card details.

The Cards tab becomes the primary visual workspace. Commander cards remain visually distinct from
the main deck. Existing compact columns become the List view rather than being removed. Grouping
supports the current tag and type concepts; the initial grouping follows the current stored deck
preference when valid and otherwise defaults to type. Existing non-card tabs remain available but
are visually subordinate to the main card workspace.

Analytics remain accessible from the existing statistics surface. Wide desktop layouts may retain
a compact analytics rail, but it must not reduce the visual card workspace below a useful width.
On narrower layouts, analytics stay behind their existing modal or collapsible entry points.

## Collection Detail Page

The collection page adopts the same header, sticky toolbar, grid, list switcher, and card-detail
behavior. It retains rename, import, export, add-card search, type filtering, price filtering,
pagination, quantity changes, removal, foil and printing information, price, and deck-membership
information.

Collection tiles display artwork, quantity, foil treatment, price, and deck-membership status.
Quantity controls are directly reachable without opening card details. Existing collection rows
become the List view for dense inventory management.

Pagination continues to be server-driven at the current page size. Changing filters resets to the
first page. View changes never trigger an API request or alter pagination state.

## Builder Deck Drawer

The closed bottom bar becomes a concise deck summary containing:

- current and target card counts;
- compact progress for the most important deck targets;
- game-changer status when relevant;
- an explicit `View deck` control and expansion indicator.

On desktop, activating it opens a right-side drawer. The main builder remains visible so users keep
their recommendation and stage context. On mobile, the same surface opens as a near-full-screen
bottom sheet with a clear title area and close control.

The drawer reuses the deck workspace's toolbar, Grid/List views, card tiles, compact list, and card
mutations. It also retains the current theme targets, type counts, mana curve, add-card search,
planned cuts, quantity changes, card detail behavior, and undo support.

The drawer closes through its close button, Escape, backdrop activation, or browser back. Opening
locks background scrolling. Focus moves into the drawer, remains within it while open, and returns
to the trigger when closed. Desktop and mobile use the same content component inside different
responsive shells.

## Component Boundaries

The refactor introduces a small shared presentation layer:

- `CardWorkspaceToolbar` owns workspace controls and reports typed preference changes.
- `VisualCardGrid` owns responsive grid layout and empty/no-results presentation.
- `VisualCardTile` renders shared artwork and badge structure with injected domain actions.
- `DeckWorkspace` adapts deck data, grouping, commander handling, and deck mutations.
- `CollectionWorkspace` adapts collection data and inventory mutations.
- `DeckDrawer` owns responsive overlay behavior, focus, scroll locking, and browser history.

Deck and collection domain types remain separate. Small adapter functions produce the minimal
display data required by shared visual components. There is no new universal card domain model and
no API or database change.

The existing compact deck columns and collection rows remain the List implementations. Current
filtering and preference utilities are extended where appropriate instead of introducing a new
state-management library.

## State and Data Flow

- Page components continue to own API loading and mutation callbacks.
- Workspace components receive domain data and typed callbacks as props.
- Shared visual components do not call the API.
- View, sort, and grouping preferences are stored locally with namespaced keys for deck,
  collection, and builder contexts.
- Search and purely visual sorting/grouping are client-side where the complete data is already
  loaded.
- Collection filters and pagination remain server-side because only one page is loaded at a time.
- Successful mutations refresh through existing page loaders so server data remains authoritative.

## Error, Loading, and Empty States

Initial page failures retain the existing page-level error presentation. Mutation failures use the
existing toast system and leave the current cards visible. A failed optional analytics request does
not block the card workspace.

The workspace distinguishes between:

- initial loading;
- a genuinely empty deck or collection;
- no results for active filters;
- a recoverable local load failure.

Controls that submit mutations expose disabled or pending states to prevent duplicate requests.

## Accessibility and Responsive Requirements

- Interactive controls use semantic buttons, inputs, links, and dialogs.
- Every icon-only control has an accessible name and visible focus state.
- Grid/List, sort, grouping, filters, quantities, and drawer state are announced correctly.
- Keyboard users can reach all card actions without hover.
- Drawer focus is trapped while open and restored on close.
- Touch targets remain at least 44 by 44 CSS pixels where practical.
- Information never relies only on color.
- Reduced-motion preferences disable non-essential drawer and tile transitions.
- The design remains usable from narrow mobile widths through wide desktop layouts.

## Verification

Focused Vitest coverage will verify:

- first-use Grid defaults and persisted Grid/List, sort, and grouping choices;
- deck filtering, grouping, commander separation, quantities, and card actions;
- collection filtering, pagination resets, inventory metadata, quantities, and card actions;
- drawer open and close paths, focus restoration, Escape handling, and responsive shell choice;
- loading, empty, no-results, and mutation-error behavior;
- accessible names and semantic states for the primary workspace controls.

The completed refactor must pass the frontend TypeScript typecheck, lint, Vitest suite, and
production build. Existing backend behavior is unchanged and does not require new backend tests.

## Acceptance Criteria

1. Deck and collection detail pages use a shared grid-first workspace with a remembered List
   alternative.
2. Both pages retain their current domain-specific capabilities and data.
3. The builder deck surface is a desktop right drawer and mobile bottom sheet while preserving all
   current deck-browser mutations and progress information.
4. Common workspace controls and card interactions behave consistently across all three surfaces.
5. The visual system keeps MTG Helper's dark indigo palette with cleaner charcoal surfaces and
   accessible contrast.
6. No backend API, schema, or database changes are introduced.
7. Typecheck, lint, tests, and production build pass.

## Out of Scope

- Copying Moxfield's branding, exact styling, or full set of view modes.
- Visual Stacks, Visual Spoiler, drag-and-drop grouping, or arbitrary custom tags beyond current
  deck categories.
- Bulk collection editing, new import/export formats, or new collection APIs.
- New analytics, recommendation logic, or backend behavior.
- A new global state-management or component-library dependency.

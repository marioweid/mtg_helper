# Card Workspace Follow-up

**Date:** 2026-07-22  
**Status:** Approved design  
**Scope:** Collection workspace controls, builder preferences, accessibility, and housekeeping

## Objective

Close the non-test follow-up items from the Moxfield-inspired card workspace review. Collection
search, sorting, and grouping must operate across the complete server-paginated collection. The
builder must restore all workspace preferences, and the identified accessibility and lint issues
must be resolved without changing or adding test files.

## Collection API

Extend `GET /api/v1/collections/{collection_id}/cards` with optional query parameters:

- `search`: case-insensitive card-name substring search;
- `sort`: `name`, `price`, or `quantity`, defaulting to `name`;
- `direction`: `asc` or `desc`, defaulting to `asc`;
- `group`: `none`, `type`, or `set`, defaulting to `none`.

Existing type, minimum-price, maximum-price, limit, and offset parameters remain supported. Search
and filters apply to both the list query and count query. Sorting and grouping use fixed,
server-owned SQL expressions selected from allowlists; request values are never interpolated into
SQL. Every ordering ends with stable card and printing columns so pagination is deterministic.

Grouping changes the leading server-side ordering. Type grouping uses the card's primary type and
set grouping uses the collection printing's set code. The response model remains unchanged because
the frontend can derive group labels from `type_line` and `set_code`.

## Collection Workspace

Move inventory controls into the shared sticky workspace toolbar:

- a debounced card-name search input;
- a sort selector with Name, Price, and Quantity choices in useful directions;
- a labeled Type, Set, and None grouping control;
- the existing Grid/List selector and result count.

The existing add-card search remains separate because it searches the global card catalog rather
than the collection. Type and price filters remain in their filter panel but participate in the
same server request.

Search, type and price filters, sorting, grouping, and page are represented in URL query parameters.
Changing any of them resets pagination to page one. Browser navigation restores the corresponding
workspace state. Grid/List remains a locally persisted display preference and does not trigger a
request.

Each loaded page renders group sections in the order returned by the server. A group may continue
onto the next page; the next page repeats that group heading rather than hiding context. Both grid
and list views use the same grouping calculation.

## Builder Preferences

Extend namespaced workspace preferences so each builder context restores:

- Grid/List view;
- Type/Tag/Flat grouping where valid for the selected view;
- card sorting mode.

Changing a preference persists it immediately. Switching from List/Flat to Grid normalizes grouping
to Type, matching current behavior.

## Accessibility and Interaction Polish

- Give the deck filter input a meaningful accessible name, `name`, and autocomplete behavior.
- Add explicit dimensions and lazy loading to search-result card images.
- Replace `transition-all` with the specific animated properties and honor reduced motion.
- Give icon-only description editing an accessible name and visible focus state.
- Increase the compact cut action toward a 44-by-44 CSS-pixel target and add a visible focus state.
- Announce the temporary planned-cut undo message as a polite status update.
- Preserve existing semantic buttons, focus trapping, and destructive-action confirmation.

## Housekeeping

- Remove the two resolved bug entries from `ideas.md` while retaining the file as the bug backlog.
- Fix the unused toast declaration on the deck import page.
- Remove the unnecessary empty-object fallback in the API header spread.
- Do not alter the two backend files that Git reports as modified without a textual diff.

## Error Handling

Invalid enum query values receive FastAPI validation errors. Collection load failures continue to
use the existing page-level error presentation. Search and preference changes keep the last visible
cards until the authoritative response arrives. Existing mutation errors continue through the toast
system.

## Verification

No test files will be added or edited. The implementation must pass:

- frontend TypeScript typecheck;
- frontend lint with no warnings from the identified issues;
- frontend production build;
- backend Ruff checks for changed backend files;
- backend type checking for changed backend files when the configured checker is available.

Database-backed pytest remains outside this follow-up because the local PostgreSQL test service is
not running and the user explicitly excluded test work.

## Acceptance Criteria

1. Collection search, filters, sorting, grouping, totals, and pagination operate over the complete
   server-side result set.
2. Collection URL state survives refresh and browser navigation.
3. Collection Grid and List views render Type, Set, or no grouping consistently.
4. Builder view, grouping, and sorting preferences restore per workspace.
5. The identified accessibility and lint findings are resolved.
6. No test file is added or modified.

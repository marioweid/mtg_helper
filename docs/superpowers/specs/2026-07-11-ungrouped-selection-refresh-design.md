# Ungrouped Selection Refresh Design

## Problem

The theme manager stores both an uninitialized selection and an intentional `Ungrouped`
selection as `null`. Every mutation refreshes the admin state. During refresh, the nullish
fallback treats the intentional `null` as uninitialized and selects the first active group,
which is currently +1/+1 Counters.

## Design

- Change selection state to `number | null | undefined`.
- `undefined` means the initial catalog has not selected a default yet.
- `null` means the administrator intentionally selected `Ungrouped`.
- A numeric value means a shared group is selected.
- On refresh, choose the first non-deleted group only when the current value is `undefined`.
- Preserve both `null` and numeric selections across membership mutations and catalog refreshes.
- If a selected numeric group disappears, fall back to `Ungrouped` rather than an unrelated group.

## Alternatives Rejected

- A second initialization boolean duplicates state that the sentinel can express directly.
- Always starting on Ungrouped changes the existing initial navigation unnecessarily.

## Testing

- Initial undefined selection chooses the first active group.
- An intentional null selection remains null after refresh.
- A numeric selection remains selected after refresh.
- A deleted or missing numeric selection falls back to Ungrouped.

## Success Criteria

Changing or unassigning a source tag while viewing Ungrouped keeps the administrator in
Ungrouped and never redirects to +1/+1 Counters.

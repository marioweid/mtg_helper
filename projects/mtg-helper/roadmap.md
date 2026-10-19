# Remaining work and boundaries

This is not a historical implementation checklist. The
[README](../../README.md) and [workflows](workflows.md) describe existing functionality;
authentication, collections, playtesting, price filters, and flexible stage navigation
are already implemented.

## Open work

- **Scryfall-only labels:** canonical publication exists; legacy consumer cutover and
  removal of old classifiers/catalogs are unfinished. Preserve personal categories and
  saved intent. See the [migration plan](../../docs/scryfall-only-label-migration-plan.md).
- **Discover acceptance:** default-off commander-only implementation exists. Source readiness,
  separately approved live spending, semantic usefulness, and real application latency still
  need evidence. See the [operating contract](../../docs/recommendation-pilot-contract.md).
- **Broader recommendations:** deck-aware source-backed discovery, New Cards migration to the
  shared core, preview/special-product coverage, and untouched-strategy evaluations are not
  delivered by the first Discover pilot. See [direction and limits](../../docs/recommendation-vision-and-proof.md).
- **Planned-change regressions:** historical checks report singleton-quantity expectation
  failures in `backend/tests/test_planned_changes.py`; reverify before claiming a green
  broader suite. See [recorded verification](../../docs/new-cards-pilot-checks.md).

Old experiment budgets and implementation reports do not authorize new paid calls,
production writes, deployments, or account enablement. Confirm those actions separately.

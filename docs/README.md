# Documentation guide

## Current application and operations

- [README](../README.md): features and development entry points.
- [VERIFY](../VERIFY.md): boot, tests, local/live database safety, and stopping containers.
- [Operations](../OPERATIONS.md): production deployment, sync, and tracing.
- [Architecture](../projects/mtg-helper/architecture.md),
  [API](../projects/mtg-helper/api-design.md),
  [data model](../projects/mtg-helper/data-model.md), and
  [workflows](../projects/mtg-helper/workflows.md): current implementation guides.
- [Remaining work](../projects/mtg-helper/roadmap.md): known unfinished boundaries.
- [New Cards contract](new-cards-pilot-contract.md): physical-deck, released-card pilot.
- [Discover contract](recommendation-pilot-contract.md): default-off source-backed pilot.
- [Recommendation direction](recommendation-vision-and-proof.md): future scope and evidence limits.
- [Scryfall migration](scryfall-only-label-migration-plan.md): unfinished consumer cutover.
- [Publication staging](scryfall-label-staging.md): isolated staging procedure.

## Historical evidence

[New Cards verification](new-cards-pilot-checks.md), the
[October 13 publication release](scryfall-publication-production.md), and `research/`
record checks at specific dates, not current deployment state or fresh approval to spend/deploy.
Research JSON, prompts, rules, and outputs are retained because evaluation scripts and tests
use them. Some full-source replays also require ignored, hash-matching bulk archives; a clean
checkout alone is not enough for those replays. Preserve single-use paid-call ledgers.

Use application source, generated OpenAPI, dependency manifests, and Compose files to verify
current behavior. Keep temporary agent plans, handoffs, and run reports local and ignored.

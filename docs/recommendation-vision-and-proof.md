# Recommendation direction and evidence

## Current implementation

The source-backed **Discover** pilot is implemented and default off. Its
[operating contract](recommendation-pilot-contract.md) is the reference for current behavior:
commander-only nonland discovery, an optional three-strategy draft, explicit card generation,
bounded spending, private diagnostics, and user-approved pending additions.
Physical/planned cards are exclusions, not evidence of deck support. This is not a replacement
for the builder, Coach, Community Picks, or the physical-deck New Cards evaluator.

## Product direction, not delivered scope

Keep local browsing, inspection, and explicit deck edits useful without waiting for AI.
Use source facts for card characteristics and query execution; use bounded, requested AI
work for contextual judgment. Queries generate candidates, not proof of fit. Literal
quotations establish provenance, not correct rules interpretation.

Future deck-aware work must distinguish:

- **Physical:** current cards and quantities.
- **Projected:** physical cards minus selected cuts plus selected additions.
- **Owned:** available inventory, not cards already in the deck.

Prefer runtime searches over source facts to universal AI-assigned card capabilities.
Do not hardcode commander interactions to improve a benchmark. For release discovery,
enumerate the declared eligible pool and report assessed/pending/failed coverage rather
than silently filtering out unfamiliar mechanics. No full-catalog AI sweep is implied.

## Preserved evidence

These are completed, bounded experiments, not live product guarantees:

| Experiment | Finding |
|---|---|
| [New Cards v2](research/new-cards-spike-2026-10-05/quality-v2-report.md) | Better identity binding did not resolve rules mistakes. |
| [Low/high reasoning](research/new-cards-spike-2026-10-05/quality-v3-report.md) | Neither evaluator met trusted-recommendation acceptance; more reasoning increased latency. |
| [Direct deck recovery](research/deck-recovery-smoke/README.md) | Useful partial Yuna/Meren recovery, not complete discovery or interactive proof. |
| [Luna/Terra planning](research/commander-discovery-smoke/README.md) | Source-grounded discovery found useful cards but retained query and interpretation errors. |
| [Partial Sol run](research/commander-discovery-sol/README.md) | A timeout left unknown billing; its single-use ledger remains stopped. |
| [Sol assessments](research/commander-discovery-sol-assessment/README.md) | Stronger spot checks, not complete coverage or an overall pass. |
| [Refined Luna](research/commander-discovery-luna-refined/README.md) | 122/128 grounding checks, still incomplete queries and material rules errors. |

Research scripts, fixtures, frozen outputs, and spending receipts remain available for
regression checks. Yuna, Meren, and Saheeli are discussed regression cases, not untouched
holdouts. Model comparisons do not by themselves authorize changing the application model.

## Remaining proof

- Real application usefulness, semantic correctness, latency, and operator/browser acceptance.
- Unused-strategy tests, including pip/devotion and cascade-versus-cost cases.
- A fully declared release-pool evaluation with honest coverage and reviewed false negatives.
- Separate design/approval for physical/projected-deck advice and migration of New Cards.
- Preservation of ownership, current eligibility, origin flags, and atomic plan completion.

The old paid authorizations are consumed or stopped. Preserve receipts; obtain new bounded
permission before further model experiments. Never reset a ledger to retry an unknown-billed
request. This direction does not authorize deployment, destructive migrations, live account
enablement, or a broad recommendation rewrite.

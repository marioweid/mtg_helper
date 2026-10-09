# Commander discovery regression fixtures

Public source-only Meren and Saheeli scenarios for the separately authorized eight-call experiment.
These commanders and examples have already guided design; they are not untouched holdouts.

- `cases.json`: commander/goal plus evaluator-only diagnostic names and manual semantic checks.
  Planners receive only source commander facts and the goal. No diagnostic names/checks or reference
  decklist are sent. Diagnostics include useful, limited and counterproductive candidates.
- `rules.json`: nine exact excerpts from the official 2026-09-25 Comprehensive Rules, with the
  download's SHA-256 and dated source URL. Provided only during assessment, not blind planning.
  This supplies context, not a complete rules engine or a guarantee about novel keywords.

The shared assessment pool deliberately includes these diagnostics. Its recommendations are not
proof that the model discovered them: see separate query/nominated/shortlist provenance.

Protocol and preserved outputs: `docs/research/commander-discovery-smoke/`.
No production data, feature changes, community retrieval or embeddings are involved.

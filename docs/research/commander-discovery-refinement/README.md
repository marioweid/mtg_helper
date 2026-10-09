# Separate pipeline refinement — Luna baseline

## Scope and authority

The user approved refining the experimental pipeline **outside the application** until testing
establishes a grounded base. After clarification, the user chose **Luna**, the cheapest measured
model, to drive refinement. Compare Sol/Terra later using the same frozen improved pipeline.
No model weight training is proposed; this is pipeline and prompt refinement.

No production model switch, app integration, deployment, database writes or new paid requests
occurred. Earlier live budgets remain exhausted and the original Sol timeout remains unpriced.
Fresh paid experiments still need bounded authorization; no existing ledger may be reset or resumed.

## Implemented offline foundations

`backend/scripts/commander_discovery_refinement.py` provides:

- A request-specific response schema: one mandatory assessment property per supplied candidate,
  no extra candidate properties, and rankings restricted to bare supplied IDs.
- Duplicate JSON property rejection before model validation. Silent overwrites are not coverage.
- Reuse of the unchanged original literal quotation/fit validation. A bad candidate quotation
  still fails that candidate, not its valid neighbors. Output conformance is not rules accuracy.
- Literal lookup across the pinned full official rules text, native IDs and unrestricted glossary
  titles, with total counts, explicit truncation, resumable results and per-operation failures.
- An extended planning schema allowing rules searches, and local execution of card/rules searches
  into observations that can feed a subsequent planning step.
- Actual card query totals, invalid/zero-result feedback, two complete source samples per query,
  and data-derived Oracle line prefixes. No model-produced role labels or diagnostic verdicts.

The official source is the same September 25, 2026 snapshot used by the earlier comparison:
`https://media.wizards.com/2026/downloads/MagicCompRules%2020260925.txt`.
The complete 977,752-byte file is cached locally at
`backend/.cache/commander-discovery/rules-20260925.txt` and verified against SHA-256
`8d860e451f20f38865b725b42d82feb714c725373dd8f3b32b8652b3eeb070ca`.
The corrected index has 3,907 native rule/glossary entries. This is not a curated mechanic whitelist;
new source formats may still require parser changes. Rule examples stay with their native rule.

## Offline replay

From `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_refinement
uv run --no-sync pytest -q -W error tests/test_commander_discovery_refinement.py
```

The CLI requires the pinned existing card/rules caches and prior Luna receipts. It reads no API
credentials and has no live option. It creates:

- `protocol-v2.json`: frozen model intention, source hashes and refined planning/review schemas.
- `feedback-v2.json`: deterministic observations for the original Luna Meren/Saheeli plans.

The initial `protocol.json` / `feedback.json` draft remains archived, not overwritten. Independent
review found a missed multi-letter rule suffix (`704.5aa`); v2 corrects it and lets planning revisions
supply rule continuation cursors. Both regressions failed before the fixes and now pass.

Old plans did not request rules lookup, so their replayed rule-search arrays are empty. Unit tests
exercise that capability separately. The CLI does not synthesize a new Luna plan or repair old
outputs. Prior experiment JSON is unchanged. Free source downloading was not a model request.

## Follow-up experiment

The separately guarded [six-call Luna run](../commander-discovery-luna-refined/README.md) is now
completed for $0.03395705; its authorization is consumed. Grounding improved, but semantic and
discovery failures remain; this does not approve app integration. Its frozen workflow follows:

A separately guarded Luna run: initial plan/rules requests → actual local observations →
one bounded planning revision → discovery → contextual assessment. Keep every input, response,
search and failure. Declare how revision replaces/retains searches before execution; distinguish
matching from independent admission, forced diagnostic inclusion and ranking. Preserve the same
frozen comparison setup when other models are later evaluated.

Planning should inspect resources, thresholds, timing and modifiers without commander-specific
synergy hints. Full-source lookup provides access, not guaranteed discovery: eight returned rule
entries and sampled card results are not exhaustive; a model must refine or request more.

Before paid execution, freeze prompts, call/token/time limits, standard-tier pricing, reservation,
a fresh single-use ledger and an explicitly approved budget. Strict response schemas may increase
input size. At this offline-foundation checkpoint, no improved latency, cost or semantic quality had been
measured. Its scoped checks: 119 offline tests passed, Ruff lint/format and `ty` passed. A deliberate feedback-truncation mutation
also made its regression fail before restoration.

A grounded base needs separate evidence for useful admission, correct rules explanations, honest
pending/failed/uncertain coverage, latency and cost. Retain discussed cases as regressions; include
an unused strategy and a fully declared small release pool before proposing app integration.

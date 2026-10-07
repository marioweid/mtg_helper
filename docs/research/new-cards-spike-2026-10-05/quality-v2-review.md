# Revised evaluator — predefined review protocol

Defined before the v2 paid run on 2026-10-05. This is a remediation/regression experiment,
not an unseen test set. The prompt explicitly addresses failure classes seen in v1.

## Fixed comparison

- Same four physical decks, same fourteen candidates per deck, same predeclared label controls.
- Same Scryfall export, verified against the baseline archive SHA-256 before restoring missing
  characteristics. Existing card facts must match exactly. No new source downloads or user data.
- Same `gpt-5.6-luna`, low reasoning/verbosity, 7,000 output-token limit, `store=False`, no retries.
- At most eight requests: forward/reverse candidate presentation per deck. Slot keys and schema
  property order stay fixed across the pair. Thus the order experiment differs from v1; neither
  pair separates random variance from presentation effects.
- New short-key contract, evidence requirement, deterministic eligibility checks and richer
  card facts change together. This evaluates the combined repair, not each component's contribution.
- Baseline artifacts are not overwritten. `quality-v2-*` artifacts contain the new experiment.

## Acceptance checks

1. All eight responses complete; each includes exactly one result for every supplied candidate.
2. All references bind to supplied cards. Every assessment has a verified candidate quotation;
   each supporting-card reference has its own verified quotation. Unknown/null facts cannot
   validate a quotation. Face-specific evidence must match the referenced face.
3. No positive label violates known legality, color identity or physical-deck duplication.
4. Check broad historical label agreement separately from semantic correctness. Keep all-label
   Ashnod's Altar controls out of the label denominator, as in the corrected v1 summary.
5. Review the following known-error cases in **both** directions, regardless of their label:
   - Wizard's Staff in both Alela decks: ordinary Equip {3} is available; Alela's creature type
     does not make the Equipment unusable. A rejection needs a real opportunity-cost argument.
   - Fateful Discovery in both Alela decks: distinguish artifact entry from casting; creating
     artifact tokens does not directly trigger Alela. Spell tokens/copies need their own wording.
   - Emrakul, the Exigent Doom in Camellia: ward's sacrifice is the targeting opponent's cost,
     not a maintenance demand on its controller.
   - Ashnod's Altar in Camellia: ordinary Squirrels are not Food by default, but supplied Food
     creatures can be sacrificed and can trigger Camellia. No invented repeatable loop.
   - Mirkwood Bats in Camellia: no invented body or unsupported token-trigger restrictions.
6. Report new concrete rules errors found while reviewing the outputs. Correct quotations do
   not prove that an interpretation is correct. A card label can be plausible for a wrong reason.
7. Record actual usage, completion status, latency, conservative estimated cost and label drift.

Passing this small, known-case experiment is not production approval. Full-pool recall,
independent decks/holdouts, previews/novel keywords and release normalization remain open.

## Reference for the generic ward rule

Wizards, [Introducing Ward](https://magic.wizards.com/en/news/card-preview/introducing-ward-2021-03-25):
ward counters an opponent-controlled targeting spell/ability unless that player pays the ward cost.
No per-card expected label or example answer is added to the model's prompt.

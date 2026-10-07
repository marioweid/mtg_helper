# v3 — predefined low/high reasoning comparison

Written before paid execution. The actual run was **2026-10-06**; the original header's date was
corrected after checking the run timestamp. Criteria and the hashed spec were not changed.
Candidate choices, broad expected labels and semantic checks are frozen in `quality-v3-spec.json`.
The model never receives that rubric or label metadata.

## Question and controls

Does **high reasoning**, rather than another prompt rewrite, reduce material rules mistakes compared
with low reasoning on identical inputs?

- Same `gpt-5.6-luna` model and exact v2 prompt, same evidence schema and deterministic gates.
- Four existing synthetic 100-card physical decks; these are **not unseen decks**.
- Eight candidates per deck: **19 holdout card/deck cases and 13 regression cases**, 32 per arm.
  Every holdout identity is absent from *all* earlier candidate and physical-card inputs. These are
  historical diagnostic cards, not a representative sample of newly released cards or preview rules.
- Same frozen Scryfall export. Complete v2 characteristics and separate face facts retained.
- Each pair has exactly the same candidate order, payload, schema and 16,000 output-token ceiling.
  Only `reasoning.effort` changes. The larger ceiling gives hidden reasoning room without giving
  one arm a different limit. This is not a direct repeat of v2's 14-candidate/7,000-token requests.
- Eight calls maximum: one per deck/arm. First-arm order is low/high, high/low, low/high, high/low
  across the four decks. No reversal test, automatic retry, repair call, or replacement call.
- `store=False`, verbosity low, no tools, no production database or private deck data.
- Full-plan conservative reservation: **$0.251433**, below the **$0.50 estimated-spend ceiling**.
  Reserve input bytes as tokens plus 2,048 framing tokens and the full output allowance. This is
  deliberately loose, not an invoice guarantee. Actual usage is retained. Missing usage, provider
  errors, incomplete/invalid output or a cost exceeding its reservation stops remaining work.
- Exclusive results creation prevents a second process or casual rerun from repeating the budget.
  Attempts are checkpointed before sending; interruption does not authorize a resume.

Model support and pricing were checked against the installed SDK and
[official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna.md): high reasoning is
supported; $0.20/M ordinary input, $0.02/M cached input, $1.20/M output; reserve all input at $0.25/M.
No new dependency, model rollout, or deployed configuration change is part of this experiment.

## Evaluation and acceptance

1. Both arms must return complete candidate coverage. Report reference/evidence contract failures
   separately from interpretation errors; keep invalid outputs in the semantic review.
2. Compare broad labels separately for holdouts and regressions, excluding all-label controls.
   Missing results remain misses. Several labels intentionally allow Strong or Worth testing;
   broad label agreement is **not accuracy, precision or recall**.
3. Review all 64 judgments against card facts and physical support. Primary concern is a **material
   factual contradiction**: wrong trigger, payer, restriction, identity, characteristic, face access,
   card-text substitution, or invented support that changes the usefulness/limitation explanation.
4. Assess novel holdouts and known regressions separately. An omitted rule is not a demonstrated
   repair. Do not demand every possible rule be restated; distinguish a correct central mechanism
   with reasonable brevity from avoiding the key question or inventing facts.
5. Keep subjective opportunity-cost disagreement separate from concrete rules errors. A reasonable
   five-mana caution need not receive Strong simply because an earlier broad control expected it.
6. Obtain an independent **arm-blinded** review: shuffled sample IDs, judgments and source/rubric,
   without effort labels or runtime/token data. The owner checks concrete findings against sources.
   This is an agent review, not certified human rules-judge adjudication. Wording can still make
   the arm partly inferable; blinding is not guaranteed perfect.
7. High reasoning is promising only if it reduces material errors without sacrificing coverage and
   avoids material contradictions in positive recommendations. Any surviving wrong Strong/Worth
   testing explanation blocks describing that configuration as production-ready.
8. Record completion, evidence validity, actual usage including reasoning tokens, latency and cost.
   One response per arm/deck cannot establish statistical superiority, stability or full-pool recall.

No follow-on paid work is authorized by a disappointing or interrupted result. Even a clean pilot
would still need real/user-approved and unseen decks, full-pool recall, novel previews, partner
commanders, constraints/pending changes, and main-playable-release normalization before rollout.

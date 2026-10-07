# New Cards: low versus high reasoning — 2026-10-06

## Decision

**Increasing reasoning alone did not make this evaluator reliable enough to ship.** High reasoning
caught a meaningful deck-constraint violation, but still invented a supplied characteristic and
misstated a rules restriction. It also produced more evidence-contract failures and was much slower.
Neither arm passed the [predefined acceptance checks](quality-v3-protocol.md).

Eight authorized calls ran starting at **2026-10-06 06:46:35 UTC**, with no retries or replacement
calls. Conservative estimated token cost was **$0.0830013 total**, below the $0.50 estimated ceiling.
No production database, user deck, application service, model default or deployed setting changed.
Earlier experiment artifacts remain preserved.

## Controlled comparison

- Same `gpt-5.6-luna`, exact v2 prompt, evidence schema, deterministic eligibility checks, low
  verbosity, `store=False`, and no tools.
- Same four synthetic physical decks. Each arm assessed eight candidates per deck: **19 holdout
  card/deck cases and 13 regression cases**, 32 judgments per arm.
- All nineteen holdout identities were absent from every previous candidate and physical-card input.
  These are candidate holdouts, **not unseen decks**, and not a representative new-release pool.
- Original Scryfall Oracle snapshot was verified against its archived SHA-256. Rich characteristics
  and face facts were retained. No fresh source downloads or new dependencies were needed.
- Each pair had byte-identical payload and schema, the same order and the same 16,000 output-token
  ceiling. Only `reasoning.effort` changed. First-arm order was counterbalanced across decks.
- The higher token ceiling allows hidden reasoning in both arms. The old v2 run had fourteen
  candidates and a 7,000-token ceiling; do not treat this as a direct repeat of v2.
- Expectations and rule checks were frozen before execution in `quality-v3-spec.json`, separately
  from model input. They were not modified to improve the observed scores.

The code reserved **$0.251433** before starting, conservatively counting input bytes as tokens plus
framing and maximum output. Exclusive results creation and pre-call attempt checkpoints prevent
casual repetition/resume. Provider failures, missing usage, incomplete/invalid output or spend above
reservation stop subsequent calls. This is an estimated-spend guard, not an invoice guarantee.

## Measurements

| Measurement | Low | High |
| --- | ---: | ---: |
| Calls / completed responses | 4 / 4 | 4 / 4 |
| Correctly bound candidate judgments | 32/32 | 32/32 |
| Whole responses passing all evidence checks | **4/4** | **2/4** |
| Individual judgments passing mechanical checks | 32/32 | 30/32 |
| Broad scored holdout-label matches | 15/15 | 14/15 |
| Broad scored regression-label matches | 8/8 | 8/8 |
| Independently flagged factual-error judgments | **3/32** | **2/32** |
| Judgments marked unclear | 2/32 | 1/32 |
| No material error observed | 27/32 | 29/32 |
| Input tokens | 51,393 | 51,393 |
| Total output tokens | 7,297 | 40,457 |
| Included reasoning tokens | 1,287 | 33,978 |
| Non-reasoning output tokens | 6,010 | 6,479 |
| Median request latency | **17.4645 s** | **93.089 s** |
| Latency range | 16.673–18.505 s | 60.193–143.965 s |
| Conservative token-cost estimate | **$0.02160465** | **$0.06139665** |

High reasoning was about **5.3× slower by median latency** and **2.8× more expensive** for these
requests. The added tokens were predominantly reasoning, not longer visible answers.

All-label controls are excluded from broad-label denominators, but all 64 judgments were reviewed
for meaning. High's single broad holdout-label miss was Trading Post: Reject rather than the
predeclared Strong/Worth testing range. A four-mana, tap-limited value engine can reasonably be
rejected on opportunity cost; the reviewer did not classify that choice as a rules error.

**None of these counts is recommendation precision, recall or calibrated semantic accuracy.**
This is one observation per deck/arm, with synthetic decks and selected rules cases. The single-judgment
net error-count difference does not establish statistically reliable superiority. V3's cases and
predeclared ranges differ from v2's, so their broad-label totals are not directly comparable.

## Independent arm-blinded review

The reviewer saw only shuffled sample IDs, judgments, supplied card/deck facts and private semantic
checks. Effort labels, latency and usage were withheld until the classifications were returned.
The owner then checked the findings against the inputs. This was an **independent agent review**,
not human rules-judge certification; wording can still partly reveal which arm reasoned more.

Full findings: [quality-v3-blind-findings.md](quality-v3-blind-findings.md).
Machine-readable classifications and unblinded counts: `quality-v3-semantic-review.json`.

### Concrete errors that remained

| Sample | Arm / cohort | Card | Source-grounded problem |
| --- | --- | --- | --- |
| S05 | Low / regression | Mirkwood Bats | Says “only 2 toughness”; supplied body is **2/3** |
| S28 | High / regression | Mirkwood Bats | Repeats the same incorrect toughness despite richer input and high reasoning |
| S29 | Low / holdout | Deekah, Fractal Theorist | Extends Talrand's Drake trigger to ordinary spell copies; Talrand triggers on casting only |
| S44 | Low / holdout | Ygra, Eater of All | Strong recommendation misses a current-deck infinite combo despite the explicit no-combo goal |
| S60 | High / holdout | Ondu Spiritdancer | Says the ability only triggers once per turn; the restriction is on choosing to make the copy |

For Ondu Spiritdancer, declining an early enchantment's copy does not prevent copying a later one
that turn. “Do this only once each turn” is not the same as “This ability triggers only once each
turn.” Its core token-copy/Alela explanation was otherwise correct.

The Bats and Spiritdancer errors do not prove that their positive *labels* are wrong. They do prove
that even quote-backed positive *explanations* remain unreliable. All five flagged judgments passed
their individual mechanical checks. Discarding entire failed batches would still retain the
Spiritdancer error in high's otherwise contract-valid Alela enchantments response.

### A genuine improvement from high reasoning

High correctly rejected Ygra based on a closed loop already supported by the physical deck:

1. Ygra makes Camellia's Squirrels Food artifacts.
2. Sacrifice one to existing Viscera Seer without mana or tapping.
3. Camellia replaces the sacrificed Food with another Squirrel, also Food.
4. Repeat; existing Nadier's Nightblade drains on each token leaving.

No other candidate is assumed present. High explicitly recognized this conflict with the deck's
no-infinite-combo goal. Low instead called Ygra Strong and blurred Nightblade's token-only condition
into “Food or token.” High also correctly separated Deekah's copy trigger from Talrand's cast trigger.

High's Emrakul explanation correctly assigns the ward payment to the targeting opponent, and its
Altar caveat specifically excludes **noncreature** Foods rather than all Foods. These are useful
repairs, not evidence that every interaction or regression is solved.

### Ambiguity and excessive caution

- **S50, low Emrakul:** correctly notes no printed cost reduction, but its wording could also deny
  the extra land mana helping reach `{10}`. Marked unclear, not silently counted correct or wrong.
- **S55/S56, both Variable Chaser:** acknowledge casting access but hedge about the association with
  Arc of Fortune. The associated sorcery and reminder provide substantial evidence; complete novel
  `prepare` rules were not supplied. Both remain unclear rather than certified correct.
- High hedges about ordinary Faerie/Soldier token mana values for Tocasia's Welcome even though such
  noncopy tokens have no mana cost and therefore mana value zero. The reviewer did not count this
  as a factual contradiction because it never says they fail, but unnecessary uncertainty can hide
  useful recommendations. More reasoning did not simply remove uncertainty.

By cohort: low had **2 flagged holdout errors and 1 regression error**; high had **1 and 1**.
Neither arm eliminated the known Bats failure, and high introduced its own holdout restriction error.

## Mechanical failures are separate

High omitted evidence for a declared support in two judgments:

- Alela artifacts / Surgical Precision: referenced **Night's Whisper** without quoting it.
- Camellia / Ruthless Technomancer: referenced **Camellia** without quoting her.

The sources exist; their omission is an evidence-contract failure, not an invented identity or an
independently established false explanation. Low had neither omission. No literal quotation
substitution was detected in either arm.

## Artifacts and verification

Archived under this original spike directory to keep the experiment lineage together:

- `quality-v3-spec.json`, `quality-v3-protocol.md`: pre-run choices and acceptance checks.
- `quality-v3-cases.json`: frozen model facts plus private expectations/checks.
- `quality-v3-results.json`: all attempts, raw and normalized outputs, usage, settings and hashes.
- `quality-v3-summary.json`: offline completion/contract/label/token/latency metrics.
- `quality-v3-blind-review.json`: the exact arm-hidden review bundle.
- `quality-v3-blind-findings.md`, `quality-v3-semantic-review.json`: returned classifications/findings.
- `quality-v3-blind-key.json`: mapping released only after the review was complete.

The executed prompt is embedded in the results and exactly matches archived `quality-v2-prompt.txt`.
Pairwise payload/schema hashes, case/spec hashes and raw-to-normalized validation replay all match.
Each archive copy matches its ignored-cache source. The protocol's initial date typo was corrected
from October 5 to the actual **October 6** run date; criteria and the hashed JSON spec stayed unchanged.

**104 offline tests pass**, plus scoped Ruff lint/format and ty checks. Tests cover identical paired
requests apart from effort, counterbalancing, budget/input limits, refusal of retries or duplicate
runs, pre-call interruption checkpoints, missing usage/provider failures, holdout overlap, immutable
fixtures and partial-result denominators. An in-memory budget-guard mutation made its regression
fail; source files were never changed and HTTP was mocked during that check.

From `backend/`, offline only:

```bash
# Requires the original cached bulk export; will not overwrite changed frozen inputs.
uv run --no-sync python -m scripts.new_cards_reasoning_spike
# Needs only quality-v3-cases.json and quality-v3-results.json in the ignored cache.
uv run --no-sync python -m scripts.new_cards_reasoning_spike --summarize
uv run --no-sync pytest -q tests/test_new_cards_data_spike.py \
  tests/test_new_cards_quality_spike.py tests/test_new_cards_evidence.py \
  tests/test_new_cards_reasoning_spike.py
```

Replay elsewhere by copying the archived v3 cases/results into `backend/.cache/new-cards-spike/`.
No API key or bulk archive is needed for summary replay. The eight-call authorization is exhausted.

Prices were checked again against the official model documentation linked in the results: all input
conservatively at $0.25/M, output at $1.20/M. Estimates exclude this coding session and agent-review
costs and are not invoices. No production or full-feed latency/cost measurement is claimed.

## Next decision

Do **not** switch the application to high reasoning on this evidence. Keep the short-key identity
binding and deterministic eligibility checks, but separate exact facts from generated prose and
reduce redundant fields the model must keep consistent. Avoid another round of tailored prompt
warnings: even the explicitly supplied toughness was still misstated.

Any further paid comparison should test a different model/approach under new authorization, rather
than assuming still more reasoning solves this model's errors. Main-playable-release normalization,
new/unseen and user-approved decks, full-pool recall, preview rules, partners and pending changes
remain unproven. No production UI or recommendation rollout is approved by this pilot.

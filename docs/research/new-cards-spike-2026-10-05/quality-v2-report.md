# New Cards evaluator v2 — measured follow-up

## Decision

**Identity binding is repaired in this run; rules explanations are still not safe to ship.**
A more constrained output format and explicit source quotes do not make this model's interpretations
reliable. Some incorrect explanations passed every mechanical evidence check, including Strong fits.

Eight newly authorized calls ran on 2026-10-05, starting at **12:56:45 UTC**. There were no retries
or additional benchmark calls after them. The original eight-call baseline remains unchanged.
No production database, user deck, application service, or deployed model/configuration was changed.

## What changed

- Each candidate has a required `C01`-style property in a strict schema, rather than a free-form
  copied Oracle UUID. Code binds each slot to its original identity after parsing.
- Physical supports use enumerated `D00`-style keys. Another candidate is not current support.
- Each result includes candidate evidence and evidence for every referenced support. Quotes must
  occur in the exact supplied field, allowing only whitespace normalization. Face indices are checked.
- The frozen Scryfall Oracle export restores power, toughness, loyalty, defense, colors, keyword
  lists and separate face facts. Null stays null. This is richer input, not a complete rules engine
  or comprehensive external-rulings corpus.
- A deterministic check supplies and validates known color, legality and physical-duplicate issues.
- The revised prompt explicitly checks payer, event, restriction, alternative equip costs, Food
  creatures and conditional face access. It asks for a short interaction statement before the fit
  judgment. It does not contain expected labels or per-card example answers.
- Raw output, normalized output, prompt, settings, usage, status and case/request/schema hashes
  are retained. A results-existence guard prevents casually rerunning/overwriting the paid experiment.

The same four 100-card physical decks and fourteen candidates per deck were reused. Baseline facts
were checked against the original export hash before adding missing characteristics. Model, reasoning,
verbosity and output-token limit were unchanged: `gpt-5.6-luna`, low, low, 7,000.

The [review protocol](quality-v2-review.md) was written before the paid run. This deliberately repairs
known failure classes; it is **not a holdout evaluation**. Several changes landed together, so the
experiment cannot attribute improvement or failure to a single component.

## Measured comparison

| Measurement | v1 | v2 |
| --- | ---: | ---: |
| Completed provider responses | 8/8 | 8/8 |
| Entire responses satisfying original ID/reference contract | 4/8 | **8/8** |
| Expected candidate judgments with correctly bound identities | Incomplete | **112/112** |
| Entire responses satisfying the new quotation/support-evidence contract | Not measured | **5/8** |
| Individual judgments satisfying the new mechanical contract | Not measured | 108/112 |
| Broad historical-label matches | 44/46 | 44/46 |
| Comparable forward/reverse pairs | 54/56 | **56/56** |
| Changed labels among comparable pairs | 9/54 | **11/56** |
| Input tokens | 84,158 | 111,132 |
| Output tokens, including reasoning | 12,848 | 20,008 |
| Median request latency | 14.121 s | 22.146 s |
| Request latency range | 12.565–15.643 s | 20.958–28.748 s |
| Conservative eight-call token-cost estimate | $0.0364571 | **$0.0517926** |

The two v2 historical-label misses are Metallurgic Summonings: Worth testing rather than the
predeclared Strong in both Talrand runs. A five-mana-cost caveat is defensible; these misses do not
by themselves demonstrate bad recommendations. Conversely, **44/46 is not semantic accuracy**.
All-label Ashnod's Altar controls remain excluded from the denominator.

The v2 5/8 contract is stricter than the v1 4/8 contract; do not present those numbers as a direct
accuracy comparison. All v2 references identify supplied cards, but identifying a source is not the
same as quoting it, and quoting it is not the same as interpreting it correctly.

Candidate presentation reverses, but v2 slot keys and schema property order remain fixed. The v1
output ordering was not constrained this way. One pair per deck still confounds presentation effects
with sampling variance; neither result estimates a causal order-bias rate or proves stability.

Cost uses the same conservative rates, checked again against the
[official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna.md): all input at
$0.25/M, output at $1.20/M. This is not an invoice and excludes coding/review-session costs.

## What the new validator caught

Four judgments failed in three responses:

| Run | Candidate | Failure |
| --- | --- | --- |
| Alela enchantments, forward | Sai, Master Thopterist | Sol Ring referenced without its own quote |
| Alela enchantments, forward | The Lord of the Eagles | Favorable Winds referenced without its own quote |
| Alela enchantments, reversed | Surgical Precision | Quoted Prophesied End's ability as its own |
| Camellia, forward | Emrakul, the Exigent Doom | Invented board-wide −X/−X quote for Tragic Slip |

Surgical Precision actually has a toughness-4-or-greater destruction mode and a draw/lifegain mode.
The output instead describes destroying any creature and giving its controller a card if it was not
attacking. This is substantive cross-card contamination, not a quotation-formatting nit.

## Rules review: persistent failures and partial improvements

A separate read-only reviewer checked the fourteen predefined known-error assessments and the
Surgical Precision substitution against exact source facts. The owner also screened the remaining
judgments against their candidate text. This is qualitative review, not a calibrated semantic score.

- **Wizard's Staff:** both reversed runs correctly explain equipping Alela through ordinary
  `Equip {3}`. The forward enchantment run still rejects the interaction by assuming Alela is not
  the equipped creature. The forward artifact run cites Emry's activated ability as evidence for
  trigger doubling and says only one supplied creature is a Wizard, although Emry and Master of
  Etherium both are. Emry does have an ETB trigger and Staff grants prowess; do not claim Emry has
  no triggers. The actual quoted activation is not doubled by Staff.
- **Fateful Discovery:** artifact entry versus Alela casting is now distinguished. But the forward
  artifact run invents another error: Discovery supposedly does not trigger Alela when cast because
  it is not an artifact. Discovery is an **enchantment**, and Alela triggers on either card type.
- **Emrakul:** the forward Camellia explanation still treats ward as threatening its controller's
  permanents. The targeting opponent pays the ward cost; otherwise their spell/ability is countered.
  The reversed run avoids discussing ward, which is not evidence that ownership reasoning is fixed.
- **Ashnod's Altar:** both runs still say it cannot sacrifice Foods, without restricting that claim
  to **noncreature** Foods. The deck contains Tough Cookie and Gingerbrute, both Food creatures.
  Their sacrifice to Altar can trigger Camellia. “Paired with existing sacrifice outlets” is vague,
  but is not enough evidence to allege a definite double-payment or infinite-loop claim.
- **Mirkwood Bats:** the forward run invents “only 2 toughness,” despite the supplied **2/3** body.
  The reversed run correctly states 2/3. Adding characteristics did not reliably ground the prose.

Further screening found additional source contradictions:

- **Ginger, Queen of Sweets, Camellia forward:** says its Gingerbrute token is not Food even though
  the candidate's reminder text explicitly says “Food Golem artifact creature.” The reverse run
  recognizes its Food type. This is another failure of the explicitly prompted Food-creature check.
- **Prophesied End, Alela artifacts reversed:** calls this **instant** a “sorcery-speed” answer.
- **Prophesied End, Alela enchantments reversed:** invents “conditional life gain”; that belongs to
  nearby Surgical Precision, not Prophesied End. Its verified quote does not validate that caveat.

Do not publish a fourteen-case semantic pass rate: corrected claims, omissions, recurring mistakes
and new mistakes coexist within individual assessments. Even dropping mechanically invalid batches
would retain wrong Strong explanations in the mechanically valid reversed Camellia response.

## Artifacts and verification

- `quality-v2-cases.json`: unchanged benchmark identities/labels plus restored public characteristics.
- `quality-v2-results.json`: all eight raw responses, normalized judgments, failures and provenance.
- `quality-v2-summary.json`: offline numerical summary; no model calls needed to recompute it.
- `quality-v2-prompt.txt`: exact executed prompt.
- `quality-v2-review.md`: pre-run comparison rules and acceptance checks.

Verified after the run: raw outputs reproduce saved validation failures; canonical UTF-8 case,
request and schema hashes all match. On Windows, use explicit UTF-8 when loading these artifacts.

**85 offline tests pass**, including no-retry/eight-attempt behavior, repeat-run refusal, frozen-fact
mismatch, short-slot identity, missing/duplicate results, invented quotes, unplanned references,
face evidence, deterministic exclusions and incomplete-response usage preservation. Scoped Ruff
lint/format and ty pass. The required-slot test failed against v1 before implementation; an in-memory
mutation disabling quotation checking made its regression test fail without altering source files.

From `backend/`, offline only:

```bash
# Prepares v2 inputs; requires the original cached Oracle export and matching archive hash.
uv run --no-sync python -m scripts.new_cards_quality_spike
# Uses quality-v2-cases.json and quality-v2-results.json in the ignored cache directory.
uv run --no-sync python -m scripts.new_cards_quality_spike --summarize
uv run --no-sync pytest -q tests/test_new_cards_data_spike.py \
  tests/test_new_cards_quality_spike.py tests/test_new_cards_evidence.py
```

To replay the summary elsewhere, copy the archived v2 cases/results to
`backend/.cache/new-cards-spike/`. Summary replay does not need the bulk export or API key.
The eight-call follow-up budget is exhausted; `--live` is not needed for any replay/check above.

## Next decision

Keep the short-key contract and deterministic gates. Do **not** start the production UI around this
baseline or treat verified quotations as a factuality guarantee. The cheap model still confuses
neighboring card facts and basic interactions even after explicit corrective instructions.

A useful next experiment would compare a stronger reasoning configuration/model under a separately
approved budget, with these regressions plus untouched holdouts, and evaluate explanations rather
than just labels. Do not continue appending bespoke prompt warnings without a controlled test.
Main-playable-release normalization, real-deck/full-pool recall, previews/novel rules, partner decks,
constraints and pending-change behavior remain separate unresolved production requirements.

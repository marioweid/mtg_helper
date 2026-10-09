# Yuna/Meren recovery smoke test — pre-run protocol

## Authorization and purpose

The user approved **Compare Luna and Terra**: at most four API requests, no retries, conservative
estimated spending capped at $0.50. No production access or application-setting changes.

This tests whether a direct goal-driven model prompt can recover familiar nonland choices before
implementing a UI or shared search algorithm. It is not a test of the complete proposed hybrid,
interactive updates, rules correctness, new-release coverage, or win rates.

## Frozen setup

- Source: cached Scryfall Oracle export, `2026-10-04T21:01:57.080+00:00`, verified against its
  previously archived SHA-256. No fresh download or community data.
- Hidden answers: user-supplied Yuna/Meren lists under `backend/evals/deck_recovery/`.
- Targets: 65 Yuna and 66 Meren nonlands. Commanders and Guiding Hydra sideboard excluded.
- Spell-front MDFCs count as nonlands; Dryad Arbor is excluded as a land.
- Input: exact commander source facts and a short strategy brief inferred from each supplied list.
  No target names, deck manifest, or answer identities are sent to the model.
- Output: exactly 50 ranked card names and short reasons. Original ordering is retained.
- Identical inputs, schema, prompt, low reasoning, low verbosity, 7,000 maximum output tokens,
  `store=False`, no tools, and zero SDK retries for both models.
- Calls: Yuna/Luna, Yuna/Terra, Meren/Terra, Meren/Luna. This counterbalances model order; one
  observation per deck/model cannot establish causal order effects or reproducibility.
- `inputs.json` freezes exact requests, settings, source/fixture hashes, pricing and reservation.
- `results.json` is created exclusively, with checkpoints before each attempted request. Restart,
  resume, and repeated paid execution are refused. Provider failures or missing usage stop further
  paid calls; malformed model outputs are retained, not replaced.

Official model pricing checked before the run:

| Model | Uncached input / million | Conservative input / million | Output / million |
| --- | ---: | ---: | ---: |
| GPT-5.6 Luna | $0.20 | $0.25 | $1.20 |
| GPT-5.6 Terra | $2.00 | $2.50 | $12.00 |

The conservative input rate prices all input as cache writes. The four-call reservation uses
UTF-8 bytes as input tokens plus prompt/schema/framing and maximum output: **$0.2069265**.
Actual usage provides a conservative token-cost estimate, not an invoice guarantee. Coding-session
costs are not part of the application API budget. Official URLs are frozen in `inputs.json`.

## Scoring fixed before execution

- Resolve exact whole names first, then unambiguous front-face aliases; match Oracle identities.
- Check frozen-source legality, commander colors, nonland status and duplicates.
- Count each eligible exact target identity at most once, without moving later ranks upward.
- Record exact hits / 50, recovery / target count, top-ten hits, invalid/duplicate outputs,
  unresolved names, off-list alternatives, latency, tokens, and estimated cost.
- **20 exact hits:** promising initial signal. **30 exact hits:** stronger initial signal.
- Review engine-specific hits as well as staples. Off-list cards can be good alternatives but do
  not count as exact recovery. Do not require 100% recovery or inflate the candidate cap.
- Preserve incomplete/failing attempts. No prompt tuning or additional calls within this budget.

No quantitative semantic-accuracy score is claimed without human review of the explanations.
Known factual contradictions may be reported separately from a card's inclusion being reasonable.

## Replay

From `backend/`:

```bash
uv run --no-sync pytest -q -W error tests/test_deck_recovery_check.py
uv run --no-sync python -m scripts.deck_recovery_check --summarize
```

Replay needs the original cached export. Default execution is also offline and only verifies/freezes
inputs. `--live` was authorized once for this protocol; existing results permanently block reruns.

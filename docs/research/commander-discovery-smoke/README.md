# Meren/Saheeli source-backed planning and discovery — measured smoke test

## Now

**All eight authorized application calls completed; no retries. Authorization is exhausted.**
Conservative estimated API cost: **$0.33604205**, within the reserved $0.891 and authorized $1 cap.
No production model, feature, deck, deployment or database changed. The earlier four-call recovery
results and exhausted authorization were not reused or altered.

Actual plans and all sixty ranked suggestions are in [outputs.md](outputs.md). Machine outputs,
shared source facts and independent-discovery provenance are preserved alongside this report.

**Result: useful evidence, not a full pass.** Fact-fed judgment recognized important connections,
but blind planning still missed proliferate for Meren, some queries failed their strategic purpose,
and output grounding/formatting plus definite rules mistakes remain. Do not roll out a global
capability classifier or claim this demonstrates the complete proposed browsing architecture.

## Setup and timing

See [protocol.md](protocol.md), frozen before execution. Each model received the same commander-only
brief, no worked-example hints or target names. Code executed its source searches and resolved its
nominations without community data/embeddings. Both models then reviewed the same 64 candidates per
commander, including explicitly tracked diagnostic cards and eight recent samples. The reviewers
also received nine official rules excerpts; those were not supplied to planners.

| Commander/model | Planning | 64-card assessment | Combined estimated API cost |
| --- | ---: | ---: | ---: |
| Meren/Luna | 11.7 s | 58.4 s | $0.012426 |
| Meren/Terra | 15.3 s | 75.7 s | $0.144543 |
| Saheeli/Luna | 13.6 s | 61.8 s | $0.013206 |
| Saheeli/Terra | 34.0 s | 80.0 s | $0.165867 |

These are single observations, not latency distributions. The assessment workload is deliberately
large and is not the deployed New Cards batch. It reinforces keeping browsing independent of
model completion; it does not reproduce or diagnose application lag.

## What worked

### Discovery beyond the initial named cards

- **Drivnod, Carnage Dominus:** Terra's Meren death-trigger-multiplier query genuinely found it.
  It was neither a diagnostic injection nor an initial nomination. Terra ranked it seventh and
  correctly connected its additional death trigger to Meren gaining additional experience.
- **Shuri, Wakandan Inventor:** Terra's Saheeli artifact-cost-reducer query found it without an
  initial nomination. Its first observed paper release was 2026-06-26, after the documented model
  cutoff. Luna ranked it ninth from the shared supplied facts. This is promising post-cutoff-source
  discovery, not proof that the model had never encountered the design.
- **Inventor's Axe:** Terra identified a practical rate connection: with Saheeli already present,
  its one-mana artifact cast supplies one energy and its entry supplies two, enough for a combat
  copy. This is more useful than merely identifying a card as an energy card.

### Judgment from source facts

- Both reviewers connected Yawgmoth's proliferate to player experience, distinguished Beast
  Whisperer's cast-based draw from direct reanimation, and recognized that Doubling Season's
  counter clause does not double player experience.
- Terra explicitly treated Cankerbloom and Evolution Sage as experience support once provided.
  **Neither was independently shortlisted by either planner.** They were forced diagnostics;
  recognizing their fit afterward is not successful automatic discovery.
- Terra correctly explained Sundial timing: end the turn while the delayed sacrifice trigger is
  on the stack. Sundial was also a forced diagnostic, not independent planning discovery.
- For the recent `Carnivorous Cultivator // Enroot`, Terra explicitly reported uncertainty because
  Prepared/face access was not defined in the supplied rules. The data schema could carry the new
  mechanic without a special label, but rules knowledge was still missing.

These are supported targeted observations, not a quantified overall semantic-accuracy claim.

## What failed or remains incomplete

### Planning/search admission

Neither Meren plan mentioned or searched for proliferate. Generic instructions to consider resource
modifiers were insufficient. Review-stage recognition was aided by candidate text and an explicit
proliferate rule; it cannot be retroactively credited to the planners.

Terra's Saheeli ETB query required literal `enters the battlefield` and returned **zero matches**.
Current source text uses `enters`. Named nominations still supplied good ETB cards, masking this
search failure unless provenance is inspected. Another Artificer-cast query returned zero as well;
zero results alone are not necessarily an error, but the ETB query demonstrably missed its purpose.

Terra's Meren outlet query required `Sacrifice a creature` plus `Activate only` or `any time`.
Those extra wording conditions excluded canonical unrestricted outlets such as Viscera Seer and
Ashnod's Altar. Nominations rescued them. Both models also generated very broad queries whose
small hash samples cannot establish useful admission recall against thousands of matches.

Luna nominated off-color **Marionette Master** for Saheeli. Code excluded it before assessment.

### Grounding/format contract

All four reviews covered all 64 candidate keys exactly once, but none passed complete frozen
validation:

| Review | Literal quote/identity-grounded assessments | Strict accepted ranked items |
| --- | ---: | ---: |
| Meren/Luna | 61/64 | 15/15 |
| Meren/Terra | 58/64 | 0/15 |
| Saheeli/Luna | 55/64 | 12/15 |
| Saheeli/Terra | 46/64 | 0/15 |

**These are not correctness or usefulness percentages.** Many quote failures were abbreviated or
reformatted source text, such as omitting energy reminder parentheses or flattening modal bullets.
Some associated judgments can still be semantically right, but the promised exact evidence failed.
Do not weaken the frozen validator after the run to improve these scores.

Both Terra reviews returned decorated ranking strings (`Cxx — Card name`). Our schema accepted
arbitrary strings and the prompt did not explicitly constrain that field to bare IDs: this is a
harness contract weakness, not proof Terra selected nonexistent cards. The strict scorer rejected
all thirty decorated identifiers. The readable output view verifies each prefix/name or front
alias against its source but does **not** alter the raw results or mark those rankings as passed.
A subsequent protocol should constrain selection IDs explicitly.

### Supported factual mistakes in Luna/Saheeli

Targeted inspection found clear errors despite source facts and, in several cases, valid quotes:

- **Solemn Simulacrum:** calls the Saheeli copy a temporary 2/2. Saheeli makes it a 5/5.
- **Sai, Master Thopterist:** says its draw ability requires four mana. Its supplied cost is
  `{1}{U}` plus sacrificing two artifacts: two mana.
- **Decoction Module:** says returning a temporary token to hand can save it. The token cannot
  be retained/recast that way (official rules 111.8 and 704.5d). Its stated four-mana-and-tap
  activation cost is correct; do not misreport tapping as an invented cost.
- **Mirage Mockery:** gives an additional five-mana entwine cost. The supplied entwine cost is
  `{2}{U}`, three additional mana, for six total without other modifiers.
- **Torpor Orb:** says it disables Sai. Sai's supplied abilities are cast-triggered and activated,
  not creature-entry triggers.
- **Wurmcoil Engine:** the caveat requires the original creature to die. A Saheeli copy dying
  is sufficient; the original does not need to die.

Other explanations were ambiguous/incomplete rather than certified contradictions. For example,
Luna's Panharmonicon wording sounds like it doubles Saheeli's own triggers, while the caveat states
entry-only scope; Terra's "6/6 copy target" can describe the original Wurmcoil, not its copied body.
Neither reviewer explicitly explained Whirler's copy refund or independent copies escaping the
separate delayed sacrifice in its main card assessment. Record those missing explanations without
inventing additional factual-error counts.

This was targeted inspection of diagnostics, ranked explanations and recent-sample judgments,
not exhaustive certification of all 256 assessments. No automated semantic percentage is claimed.

## Conclusion and next evidence

The direction still has practical promise: source queries can surface non-nominated designs,
and models can assess fresh supplied text without requiring permanent synergy labels. Terra was
more useful on several tricky explanations here, but no general model winner or production switch
is established. Luna is substantially cheaper; that does not erase the observed reasoning mistakes.

The immediate weaknesses are **query generation and judgment reliability**, not a missing global
interaction ontology. A next bounded prototype should give planning actual query feedback and
source-language examples, make authoritative rule lookup available before planning is finalized,
and constrain selection IDs/citations correctly. Do not solve this by hardcoding "Meren wants
proliferate". Test genuine holdout strategies and complete release enumeration separately.

Any new paid run requires new authorization. Current remaining dollars do not authorize extra
requests, retries or tuning. No broad implementation is approved. Empty-feed/lag investigation
remains separate and unreproduced.

## Checks and replay

Scoped Ruff lint/format, `ty`, function-size/parameter limits, and **82 offline tests** passed
(27 discovery tests plus 55 prior regression tests). The spending/call/attribution boundary also
received one independent read-only review with no supported blockers before live execution.
That review was not certification of the resulting Magic advice.

From `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_check --summarize
uv run --no-sync pytest -q -W error \
  tests/test_commander_discovery_check.py tests/test_commander_discovery_run.py \
  tests/test_deck_recovery_check.py tests/test_assistant_quality_eval.py \
  tests/test_new_cards_evidence.py
```

Replay is offline and requires the frozen caches. **Never delete `results.json` to rerun `--live`.**

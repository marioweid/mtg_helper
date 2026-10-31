# Four-call role-search experiment

## Result — October 29, 2026

**Richer term selection is promising; the role-diversified ordering should not ship as tested.**
All four authorized requests completed with valid source selections. The predeclared experimental
package recovered more familiar cards, but the offline controls show that much of the gain comes
from replacing alphabetical ordering with existing global popularity. Forced role round-robin
adds no measured benefit over the simpler filtered-popularity ordering and surfaces harmful filler.
No application behavior, model setting, strategy, deck, or database schema changed.

### Exact-list recovery

These are reference hits among the first 50, **not precision or recommendation accuracy**. Several
off-list choices are sound alternatives. Each deck/selection arm has just one model sample on a
known regression deck; none of these measurements establishes unseen-deck performance.

| Selection / ordering | Yuna hits@10 | Yuna hits@50 | Meren hits@10 | Meren hits@50 |
| --- | ---: | ---: | ---: | ---: |
| Current automatic terms + production OR/count/alphabetical | 0 | 1 | 0 | 3 |
| Experimental terms + same production ordering | 0 | 6 | 1 | 2 |
| Experimental lane filters + same production ordering | 0 | 6 | 1 | 2 |
| Experimental lanes + round-robin, alphabetical within lanes | 0 | 1 | 0 | 1 |
| Experimental lanes + round-robin, popularity within lanes | 1 | 9 | 4 | 17 |
| Current automatic terms + popularity only (follow-up control) | 1 | 4 | 4 | 17 |
| Experimental terms + popularity only (follow-up control) | 1 | 6 | 5 | 22 |
| Experimental lane filters + popularity only (follow-up control) | 1 | 11 | 6 | 20 |

Full-pool reference coverage:

- Yuna: current terms **37/65** (2,378 matches); experimental terms **46/65** (3,094 matches);
  lane-filtered **46/65** (2,735 matches).
- Meren: current terms **23/66** (1,430 matches); experimental terms **38/66** (1,739 matches);
  lane-filtered **29/66** (1,332 matches).

The experimental menu/selection finds more reference identities, independently of ranking. But
flattening those terms into the old ranking does not consistently improve the first 50. Lane
filtering sacrifices nine Meren reference identities. Pure popularity on the experimental pool
reaches 22 Meren hits; the same approach gets only six Yuna hits. No single variant dominates both
decks, and Yuna remains below the historical 20-hit smoke target even in the best measured arm.

### What the actual model selected

- **Yuna:** creature-based mana, repeatable/given +1/+1 counters, counter sharing/counters-matter,
  and creature-scoped counter preservation/death triggers. This reaches the real counter engine
  better than the saved self-keyword criteria reproduced in the preceding diagnosis.
- **Meren:** creature sacrifice outlets, creature-based reanimation, death payoffs, enter/leave
  triggers, and sacrifice-for-mana creatures. These are recognizable complementary functions.
- **However, every emitted lane has only one OR group.** The schema and matcher support AND
  intersections, but this four-call experiment did not demonstrate automatic compound-query
  selection. Do not credit gains to intersections that the model never produced.
- The type restriction on Meren's reanimation lane excludes reanimation spells/enchantments such
  as Reanimate and Animate Dead. The selected enter/leave source tag produces only three eligible
  creatures, and the sacrifice-for-mana lane only seven. Equal round-robin gives these tiny lanes
  early slots regardless of usefulness; cardinality and source membership do not certify quality.

### Oracle-text spot-checks

Inspection used the exact source facts retained in the local result artifacts, not additional model
calls. This is a targeted review of good and suspicious examples, not a complete semantic rating.

| Card / deck | Source-grounded observation | Assessment of this search result |
| --- | --- | --- |
| The Great Henge / Yuna | Nontoken creature entries add a +1/+1 counter and draw a card; cost reduction uses greatest creature power. | Useful off-list engine support; zero exact-list credit does not make it bad. |
| Hardened Scales / Yuna | Adds one when +1/+1 counters would be put on a controlled creature. | Useful off-list counter support. |
| The Ozolith / Yuna | Preserves counters when a controlled creature leaves, then may move its counters at combat. | Reference-list engine piece surfaced by the experimental package. |
| Enduring Innocence / Yuna | Draw requires another creature entering with power 2 or less, at most once each turn. | Conditional; Yuna's two additional entry counters can prevent that draw condition. Do not count it as unconditional recursion/draw value. |
| Sakura-Tribe Elder / Meren | Sacrifices itself to put a basic land onto the battlefield tapped. | Reference-list ramp/fodder that can be reused through creature recursion. |
| Viscera Seer / Meren | Sacrifice a creature to scry 1, without a mana cost. | Reference-list reusable sacrifice outlet. |
| Artisan of Kozilek / Meren | Reanimation ability triggers **when cast**. | Meren putting it onto the battlefield does not trigger that ability. It is not the repeatable recursion engine suggested by its lane. |
| Raving Oni-Slave / Meren | Entering **or leaving** loses 3 life unless its controller has a Demon. | Clear filler problem: no Demon package is established by the commander/brief, and repeating this effect is a liability. It was the third and last card in a tiny enter/leave lane. |
| Invasion of Ikoria / Meren | Front face is a Battle; only its transformed back face is a creature. | The prototype's source type check spans all printed faces, admitting it to a creature lane. That does not make it a creature-card target for Meren in the graveyard. |
| Deadwood Treefolk / Meren | Enter/leave trigger returns another creature card to **hand**. | Potential reusable value, not direct battlefield reanimation; keep the distinction visible. |

The Raving Oni-Slave, cast-trigger and back-face examples demonstrate that valid source terms and
attractive role prose do not yet provide a reliable relevance gate. Do not deploy the generated
lanes or hardcode these named cards as exceptions to make the two-deck score improve.

### Decision

1. Keep the richer commander/source context and better source-term coverage as the promising part.
2. **Do not adopt the tested equal round-robin role ranking.** It is worse than simpler popularity
   controls on these cases and promotes the tail of very small, weakly specified lanes.
3. The next product candidate should compare informative strategy constraints plus a clearly labeled
   global-popularity prior, without treating source tag count, source strength, or a named role as
   proven fit. Front-face/access context and cast/entry distinctions need explicit handling.
4. Retain these frozen cases, then use unused strategies and human ratings before selecting a
   production ranking. The post-hoc controls guide the next hypothesis; they are not a validated
   production replacement. No additional model calls or application integration are authorized here.

### Spend, timing, and verification

- Exactly **4/4** attempted/completed requests, zero retries, zero per-card model reviews.
- **41,036 input / 1,970 output tokens**; conservative known token-cost estimate **$0.012624**.
  No unknown-cost attempt. Reserved **$0.054949**, below the approved **$0.10** ceiling. These
  estimates are not an invoice; conservative input pricing does not assume cache savings.
- Request latency: Yuna baseline **5.58 s**, experimental **6.02 s**; Meren experimental **9.75 s**,
  baseline **4.14 s**. These are individual calls, not interactive latency percentiles.
- Provider model/settings: existing `gpt-5.6-luna`, default service tier, low reasoning/verbosity,
  4,000 output-token limit, no tools, `store=false`, SDK retries disabled.
- Docker-scoped tests cover grouped matching, identity/keyword rejection, distinct-term budget,
  duplicate lanes, missing popularity, empty lanes, one-shot reservation/ledger guards, timeouts,
  and missing usage. The tests were observed red before implementing diversification and the
  popularity control. **52 scoped tests pass**, including the existing Discover application seam
  checks. Ruff lint/format, ty, function-size and positional-parameter checks pass. A final offline
  replay reproduces both `summary.json` and `controls.json` exactly without invoking the provider;
  frozen request/code hashes and the four known-cost completed attempts were rechecked.
- Paid requests and code hashes are frozen in `inputs.json`; original responses/receipts in
  `attempts.json`; predeclared ranking results/source-text evidence in `summary.json`; separately
  declared no-cost popularity controls and rank-input fingerprints in `controls.json`.
- All database reads used the explicit isolated Compose stack. Scoring replays refuse changed
  source publications or reference fixtures. Global rank metadata also affects local ordering;
  controls retain a fingerprint to detect changed ranking inputs. No live-data writes occurred.

## Frozen protocol, before paid execution

The user explicitly authorized four fresh paid term-selection calls on October 29, 2026, after
choosing the four-call option. Estimated total ceiling: **$0.10**. No retries, per-card AI reviews,
application changes, or deck writes. This is separate from exhausted historical authorizations.

- Same source publication and short historical strategy brief per deck in both arms. No hidden
  reference-card names, previous model card suggestions, or manual fixture-specific role tags
  reach the provider. Reference lists are hashed before calls and resolved for scoring afterward.
- Baseline uses the current application term request, prompt, schema, bounded menu, model and
  settings. Experimental requests use the same model/settings and eight-distinct-tag / eight-
  distinct-keyword budget. They add commander facts, source descriptions and 1-6 grouped role lanes.
- Experimental tag menu retains the first 80 baseline terms, then adds direct commander source tags,
  their immediate source parent/child neighbors, and commander-Oracle-text retrieval, deduplicated
  and capped at 160. There is no custom tag-to-strategy mapping. Descriptions are capped at 600
  characters with an explicit truncation flag. The keyword menu retains baseline terms and adds
  commander/source-text retrieval, capped at 120. No semantic correctness is asserted by retrieval.
- Within a group, tags/printed keywords are alternatives. Groups in a lane are intersected, with
  optional card-type scope; lanes are alternatives. No blanket membership-strength filter.
- Call order is Yuna baseline, Yuna experimental, Meren experimental, Meren baseline. Exactly one
  attempt each, no revisions or repair calls. Requests, schemas and code/source/fixture hashes
  freeze in `inputs.json`; `attempts.json` is created exclusively and checkpointed before calls.
- Conservative reservation uses serialized UTF-8 request bytes plus 2,000 as input-token upper
  estimates and 4,000 output tokens per call. Input upper bound is 80,000 per call and reservation
  must be <=$0.10. Pricing checked at the official model page before calls: input $0.20/M, cache-write
  upper $0.25/M, output $1.20/M. Cache savings are not assumed. Unknown usage/model/tier stops calls.
- Local eligibility is the unchanged production SQL: paper, Commander legality, commander colors,
  nonland-front designs, commander exclusion. Empty-deck exclusions keep reference recovery honest.
- Report every selection/ranking arm: baseline flat OR/count/alphabetical; experimental flattened
  terms with that ordering; lane filtering alone; round-robin lane diversification with alphabetical
  lanes; and round-robin with existing global popularity within lanes. Global popularity is not
  commander-specific synergy. No community fetches or paid per-card assessments.
- Success signal: a consistent improvement in both decks' first-50 reference recovery, supported by
  readable role coverage and Oracle-text spot-checks. Preserve failures and negative ablations.
  These are familiar regressions, not blind holdouts. A package comparison does not attribute gains
  to one prompt/menu/schema change; local ranking ablations isolate only local ordering changes.

## Docker commands

All modes run from the repo root with the isolated local publication already available. Preparation
and replay use a dummy model key. Only `--live` uses the existing key without printing it.

```powershell
docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --volume "${PWD}/docs/research/discover-relevance/role-experiment:/workspace/docs/research/discover-relevance/role-experiment" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --frozen python -m scripts.discover_role_calls
```

After offline verification, use the same command with `--live` and **without** `-e OPENAI_API_KEY=test`.
There is no resume: an existing attempt ledger refuses all paid reruns. `--summarize` replays the
saved outputs locally with no paid requests; it refuses changed sources or reference fixtures.

## Offline follow-up control, declared after the four calls

The first comparison recovered 1 -> 9 Yuna and 3 -> 17 Meren reference cards among the first 50
using role diversification plus popularity; diversification without popularity did not improve
recovery. Before attributing the gain to roles, measure popularity alone on the same frozen
baseline and experimental term pools, and popularity on the experimental lane-filtered pool.
Do not change terms, lane definitions, eligibility, model outputs or any paid artifact. This
post-hoc local control is diagnostic, not preregistered confirmation or permission for more calls.

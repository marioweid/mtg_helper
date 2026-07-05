# MTG Helper Data and Simulation Exploration

Date: 2026-07-05

This is a research/design note only. No implementation has been done.

## Short Answer

For the next step, we should focus on deterministic data and recommendation
signals before expanding the AI layer.

Recommended order:

1. Strengthen the card data pipeline with MTGJSON-derived fields where they are
   better structured than Scryfall.
2. Add draft/statistical datasets, starting with 17Lands, as separate analytics
   tables rather than mixing them into the Commander card pipeline.
3. Improve card representations using structured feature extraction, embeddings,
   and usage signals.
4. Keep MTG-Causal-RL and Forge as future simulator/rules-engine research. They
   are valuable, but too large for a first integration.

The current project already has useful foundations: Scryfall import, card
keywords, card types/subtypes, traits/token types, EDHREC services, Commander
Spellbook combo lookup, embeddings, and a goldfish playtest simulator.

## 1. MTGJSON Keywords In The Pipeline

Question: Can we take the keywords from MTGJSON in our pipeline? Is this better?

Answer: Yes, but use MTGJSON as an enrichment source, not necessarily as a full
replacement for Scryfall.

MTGJSON exposes structured card properties including `keywords`, `types`,
`subtypes`, `supertypes`, `manaValue`, `edhrecRank`, `edhrecSaltiness`,
`isGameChanger`, legalities, rulings, related cards, and identifiers. Our current
Scryfall pipeline already stores `keywords`, `card_types`, `subtypes`,
`edhrec_rank`, `game_changer`, legalities, prices, images, and oracle text.

What MTGJSON may do better for us:

- More explicit type decomposition: `types`, `subtypes`, and `supertypes`
  instead of parsing `type_line` ourselves.
- More portable bulk formats, including JSON, CSV, and database files.
- Daily update model, which fits scheduled ingest.
- Extra Commander-relevant metadata such as `edhrecSaltiness`.
- Stable all-in-one data packages that can reduce ad hoc parsing.

What Scryfall still does very well:

- Excellent card search syntax and image URLs.
- Oracle-oriented card objects that already fit our current card table.
- Reliable `oracle_id` and `scryfall_id` workflow.

Recommendation:

Keep Scryfall as the primary card identity/image/oracle source for now, then add
an MTGJSON enrichment job that joins by Scryfall identifiers or card name/set
metadata. The first useful fields to import would be:

- `supertypes`
- `types`
- `subtypes`
- `keywords`
- `edhrecSaltiness`
- `isFunny`
- `isOnlineOnly`
- `isRebalanced`
- `leadershipSkills`
- `relatedCards`

For keywords specifically, MTGJSON is not automatically "better" than Scryfall,
but it is useful as a cross-check and may reduce our custom parsing around types
and supertypes.

Best near-term implementation shape:

- Add `mtgjson_enrichment` as a separate admin job.
- Do not replace `scryfall.run_sync` immediately.
- Store raw MTGJSON identifiers/metadata in new columns or a side table first.
- Compare keyword differences between Scryfall and MTGJSON before trusting one
  over the other.

## 2. 17Lands Public Data And The Simulator

Question: Can we add 17Lands Public Data to the simulator to draft against other
decks or something like that?

Answer: Yes, but it should become a draft analytics module first. It should not
be bolted directly onto the current Commander goldfish simulator.

The current simulator is a goldfish simulator. It answers questions like:

- Do I hit land drops?
- Do I flood or screw?
- Can I cast my commander?
- Which cards are stuck in hand?
- Which colors are missing?
- How efficient is my mana curve?

17Lands data is different. It is about Limited/draft behavior and outcomes:

- Card performance by set/format.
- Pick behavior.
- Game-in-hand win rates.
- Opening hand impact.
- Color pair/archetype performance.
- Draft seat and deck context signals.

Useful things we can build from 17Lands:

- Draft pick advisor: "Given this pack and current pool, what are the best
  picks?"
- Archetype lane detector: "This draft is drifting toward UB control or RG
  stompy."
- Limited card ratings table per set.
- Simulated draft bots that pick using 17Lands-informed heuristics.
- Opponent deck pools generated from real Limited archetype distributions.

What "draft against other decks" could mean:

1. Draft bot simulator:
   The user drafts packs while seven bots make picks. Bot choices are based on
   card ratings, colors already picked, archetype signals, and scarcity.

2. Deck matchup simulator:
   Build or sample opposing Limited decks from 17Lands-like archetypes and run
   simplified games.

3. Statistical deck evaluator:
   Skip gameplay simulation at first. Score the drafted deck against historical
   win-rate signals, curve, color consistency, removal count, creature count,
   synergy, and archetype fit.

Recommendation:

Start with option 3, then option 1. Avoid option 2 until we have a stronger
rules/game model.

Near-term design:

- Add `limited_sets`, `limited_card_stats`, `limited_archetype_stats`, and maybe
  `limited_pick_stats` tables.
- Import 17Lands public data by set and format.
- Build deterministic draft scores from:
  - card rating
  - color commitment
  - archetype fit
  - curve needs
  - removal/creature fixing needs
  - duplicate/synergy bonuses
- Expose this as a draft helper before calling it a simulator.

Do not mix 17Lands data into Commander recommendations. It answers a different
format problem.

## 3. Learning With Generalised Card Representations

Question: What can we implement from this paper?

Answer: The most useful idea is not "train a big model immediately." The useful
idea is to represent cards with several feature groups so the system generalizes
to new cards.

The paper studies generalized representations for MTG cards using numerical,
nominal, text, image, and third-party usage metadata. The key lesson for us:
recommendation quality improves when card understanding is not just oracle text
or raw embeddings.

We can implement a practical version with our current stack:

### A. Structured Card Feature Vectors

For every card, compute stable structured features:

- Mana value.
- Color identity.
- Card types, supertypes, subtypes.
- Keywords.
- Power/toughness buckets.
- Commander legality.
- EDHREC rank and saltiness.
- Game Changer flag.
- Price bucket.
- Rarity.
- Text-derived tags: ramp, draw, removal, board wipe, tutor, protection,
  recursion, token maker, sacrifice outlet, payoff, enabler, finisher.

We already have parts of this: `keywords`, `card_types`, `subtypes`, `traits`,
`token_types`, tags, EDHREC rank, and embeddings.

### B. Better Embedding Text

The current embedding text is:

`name | type_line | oracle_text | Keywords: ...`

Improve it with structured labels:

- `Name:`
- `Types:`
- `Subtypes:`
- `Keywords:`
- `Commander role tags:`
- `Produces tokens:`
- `Traits:`
- `Color identity:`
- `Mana value:`

This gives the vector index richer card meaning without training our own model.

### C. Hybrid Retrieval Scoring

Blend multiple signals:

- Semantic similarity from Qdrant.
- Structured filters from Postgres.
- EDHREC inclusion signal.
- Commander Spellbook combo proximity.
- User-owned collection availability.
- Budget/price preferences.
- Deck curve and role gaps.

This matches the paper's spirit: generalized card representation beats a single
input view.

### D. Evaluation Set

Create a small benchmark:

- Given a commander and theme, predict 20 likely inclusions.
- Compare against EDHREC categories and known decklists.
- Given a deck gap, rank candidate replacements.
- Track whether accepted user suggestions improve over time.

Recommendation:

Implement the representation work as data engineering and scoring first, not ML
training. It directly improves point 1 and point 2 of our staged plan.

## 4. MTG-Causal-RL Benchmark

Question: What could we implement from here?

Answer: Borrow the measurement ideas, not the full reinforcement-learning stack
yet.

The MTG-Causal-RL benchmark models MTG as a Gymnasium environment with masked
actions, partial observations, archetypes, reward schemes, causal variables, and
policy auditability. That is powerful, but it is much bigger than our current
app needs.

Useful ideas we can implement now:

### A. Causal-Looking Telemetry For Our Existing Simulator

Add explicit factors to playtest results:

- Land count.
- Color source count by color.
- Average mana value.
- Early play density.
- Ramp density.
- Draw density.
- Interaction density.
- Tapland ratio.
- Commander mana requirements.
- Number of cards above 5 mana.

Then report which factors most likely caused failures:

- "Color screw is mostly tied to low blue source count."
- "Commander cast failures correlate with high tapland ratio and few ramp
  pieces."
- "Flood occurs because draw/ramp mix produces excess mana with no sink."

This is not true causal RL, but it gives users causal explanations.

### B. Intervention Experiments

Run counterfactual deck mutations:

- Add two lands.
- Remove two lands.
- Replace two taplands with untapped duals.
- Add two ramp spells.
- Cut top-end cards.
- Lower average mana value.

Then compare simulation output before/after.

This is very valuable and much simpler than RL.

### C. Archetype-Specific Baselines

The benchmark uses archetypes. We can do a Commander version:

- Spellslinger.
- Aristocrats.
- Voltron.
- Tokens.
- Reanimator.
- Lifegain.
- Artifacts.
- Enchantress.
- Lands.
- Control.

Each archetype gets different healthy ranges for ramp, draw, interaction,
creatures, curve, and commander cast timing.

### D. Auditability

Every recommendation should show evidence:

- Triggering metric.
- Baseline threshold.
- Candidate intervention.
- Expected metric movement.

Recommendation:

Do not implement MTG-Causal-RL as a dependency right now. Use its concepts to
make our simulator explanations more rigorous.

Good near-term feature:

`simulate_interventions(deck, interventions)` returning a side-by-side scorecard
for likely deck changes.

## 5. Forge As A Simulation Replacement

Question: Maybe we can add/change the simulation completely using Forge?

Answer: Maybe later, but not as the next move. Forge is a serious rules engine,
and integrating it would be a major architecture decision.

Forge is an open-source MTG rules engine with AI formats including Sealed,
Draft, Commander, and Cube. It has a large Java codebase and a dedicated
`forge-ai` module. It can represent real MTG game rules far better than our
current Python goldfish simulator.

What Forge could unlock:

- Real gameplay simulation instead of curve-only goldfishing.
- AI opponents.
- Draft, Sealed, Commander, and Cube simulation.
- More accurate interaction between cards.
- Potential matchups between complete decks.

Why not replace our simulator immediately:

- Forge is Java; our backend is Python/FastAPI.
- Integration means process orchestration, API wrapping, serialization, and
  possibly long-running workers.
- Licensing and distribution need review.
- Mapping our deck/card IDs to Forge card definitions may be non-trivial.
- Running many simulations may be expensive.
- Commander games with multiplayer politics are still hard even with rules.

Possible integration shapes:

1. Keep current simulator, add Forge as optional external worker.
   Best long-term shape. Our app calls a Forge service only for high-fidelity
   simulations.

2. Rewrite simulation around Forge.
   Highest fidelity, highest cost, and biggest disruption.

3. Borrow concepts from Forge but keep Python simulation.
   Lowest risk. Improve our heuristics incrementally.

Recommendation:

Do option 3 now, option 1 later. Avoid option 2 unless high-fidelity gameplay
simulation becomes the core product.

Near-term useful idea from Forge:

Keep simulation as a separate boundary. The app should ask a simulator service
for telemetry, not mix rules logic into AI prompts or deck services. Our current
`playtest_service.py` is already mostly this shape.

## Point 1: Deterministic Data First

The immediate win is a stronger deterministic data layer.

Suggested data roadmap:

1. Keep Scryfall as primary card import.
2. Add MTGJSON enrichment for structured fields.
3. Add validation reports comparing Scryfall vs MTGJSON:
   - keyword differences
   - type/subtype differences
   - legality differences
   - game changer differences
4. Add EDHREC/Commander Spellbook freshness checks.
5. Add provenance columns or tables so we know where each signal came from.

Important principle:

The AI should not infer facts that are available from deterministic data. It
should explain, compare, and ask useful questions after the facts are retrieved.

## Point 2: Recommendation Signals Second

Before building more AI, strengthen the scoring system.

Commander recommendation signals:

- EDHREC category weights.
- Commander Spellbook combo proximity.
- Card role tags.
- Deck curve gaps.
- Mana/color fit.
- User collection ownership.
- Budget/price constraints.
- Existing deck exclusions.
- Bracket/power preference.

Limited/draft recommendation signals:

- 17Lands card stats.
- Current draft pool colors.
- Archetype lane.
- Pack scarcity.
- Curve needs.
- Removal count.
- Creature count.
- Mana fixing needs.
- Synergy with already drafted cards.

These should be deterministic scores that can be inspected. AI can later explain
why the scores make sense.

## Recommended Next Exploration Experiments

### Experiment 1: MTGJSON Enrichment Diff

Goal:

See whether MTGJSON improves our current card metadata.

Output:

- A report of cards where Scryfall and MTGJSON keywords differ.
- A report of cards where our parsed `card_types`/`subtypes` differ from
  MTGJSON `types`/`subtypes`.
- A recommendation on which fields to trust.

Success:

We find fields that reduce parsing errors or add useful new ranking/safety data.

### Experiment 2: Representation Score Prototype

Goal:

Implement a deterministic card representation builder without training a model.

Output:

- One feature payload per card.
- Improved embedding text.
- A hybrid scoring function spec.

Success:

Candidate recommendations become easier to explain and test.

### Experiment 3: Simulator Intervention Report

Goal:

Borrow the causal benchmark idea without RL.

Output:

- Baseline simulation.
- Simulation after common interventions.
- Side-by-side metric deltas.

Success:

The app can say "adding two lands improves kept-at-7 by X and commander cast
rate by Y" instead of only saying "add lands."

### Experiment 4: 17Lands Draft Data Spike

Goal:

Import one set of 17Lands public data and build a deterministic Limited card
rating table.

Output:

- `limited_card_stats` rows for one set/format.
- A draft pick scorer that does not need AI.

Success:

Given a pack and current pool, the app can rank picks with inspectable reasons.

### Experiment 5: Forge Feasibility Spike

Goal:

Decide whether Forge can be used as an external simulator worker.

Output:

- Can we run Forge headlessly?
- Can we load a decklist?
- Can we run AI games or scripted tests?
- What output can we extract?
- What license/distribution constraints apply?

Success:

We know whether Forge is a future worker service or just inspiration.

## Final Recommendation

Do not rewrite the simulator now.

Do this first:

1. Add MTGJSON enrichment as a sidecar pipeline.
2. Build a structured card representation layer.
3. Improve deterministic recommendation scoring.
4. Add simulator intervention reports.
5. Add 17Lands as a Limited/draft analytics module.

Then later:

6. Use AI to explain recommendations.
7. Investigate Forge as a high-fidelity external simulation worker.
8. Treat MTG-Causal-RL as research inspiration for evaluation and causality, not
   as an app dependency.

## Step 1 Implementation Note

Started on 2026-07-05.

The first implementation step is intentionally a sidecar MTGJSON pipeline, not a
blind replacement of the Scryfall pipeline.

Implemented direction:

- Add MTGJSON AllPrintings as a configurable source.
- Store MTGJSON metadata in a separate `mtgjson_card_metadata` table keyed by
  Scryfall printing id.
- Extract keywords, types, supertypes, subtypes, saltiness, game-changer flag,
  related cards, leadership skills, and raw identifiers.
- Add an admin job that syncs MTGJSON metadata and reports differences between
  current `cards` fields and MTGJSON fields.

Decision:

We should not replace `cards.keywords` yet. We should run the diff first. If
MTGJSON has equal or better coverage, fewer parsing problems, and no meaningful
missing keyword cases, then we can safely promote MTGJSON fields into the main
card pipeline.

Likely final shape:

- Scryfall remains the source of truth for identity, oracle text, images,
  prices, and Commander legality.
- MTGJSON becomes the source of truth for structured metadata where it is more
  explicit: supertypes, types, subtypes, and possibly keywords.
- Our own parser becomes a fallback, not the primary source, for fields MTGJSON
  covers cleanly.

## Step 2 Implementation Note

Started on 2026-07-05.

The second implementation step adds a deterministic card representation layer.
This is the practical version of the "generalised card representations" idea:
make card facts explicit before asking embeddings or AI to reason over them.

Implemented direction:

- Add a `CardRepresentation` helper that combines:
  - name
  - type line
  - oracle text
  - color identity
  - mana value
  - card types
  - subtypes
  - keywords
  - role tags
  - mechanical traits
  - token types
  - EDHREC rank
- Replace the older free-form embedding text with labeled embedding text, such
  as `Name:`, `Card types:`, `Commander role tags:`, and `Produces tokens:`.
- Add compact feature labels such as `tag:ramp`, `keyword:flying`, and
  `mana_value:2-3`.
- Store the structured representation and feature labels in Qdrant payloads
  during embedding.

Decision:

This is intentionally representation-first, not ranking-weight-first. It should
improve semantic retrieval after re-embedding without changing scoring behavior
in a surprising way. Once we inspect results, the next move can be a measured
hybrid scoring update that uses representation features explicitly.

Operational note:

Cards need to be re-embedded after this change for Qdrant vectors and payloads
to use the richer representation.

## Step 3 Implementation Note

Started on 2026-07-05.

The third implementation step adds a deterministic representation-scoring lane
to hybrid retrieval. This is the first scoring change built on top of the
structured representation work from Step 2.

Implemented direction:

- Add a `RepresentationQuery` built from existing parsed query tags and
  structured type filters.
- Score candidates by deterministic overlap with:
  - role tags
  - card types
  - subtypes
  - keywords
  - traits
  - token types
- Add a small fixed representation weight to retrieval scoring.
- Reallocate that weight from semantic and tag-synergy weights instead of
  inflating total score.
- Add a `representation` signal to matching cards so this lane is inspectable.

Decision:

The representation lane is intentionally modest. It should improve ranking for
queries like "treasure artifact ramp", "flying creatures", or "food token
synergy" without overpowering EDHREC, Moxfield, semantic search, curve fit, or
color identity.

Why this matters:

This makes recommendations less dependent on embedding similarity alone. If a
card explicitly matches deterministic deck-building facts, the ranker can now
reward that match directly and explain it.

Next likely scoring work:

- Add a result-debug endpoint or admin-only trace mode showing each candidate's
  signal scores.
- Use MTGJSON-enriched supertypes/types/keywords once Step 1 diff data proves
  they are better than our current fields.
- Consider account-level tuning for the representation weight after observing
  recommendation quality.

## Sources

- MTGJSON: https://mtgjson.com/
- MTGJSON Card Set model: https://mtgjson.com/data-models/card/card-set/
- Scryfall API: https://scryfall.com/docs/api
- 17Lands Public Datasets: https://www.17lands.com/public_datasets
- EDHREC: https://edhrec.com/
- Commander Spellbook: https://commanderspellbook.com/
- Forge: https://github.com/Card-Forge/forge
- Forge AI module: https://github.com/Card-Forge/forge/tree/master/forge-ai
- Learning With Generalised Card Representations for Magic: The Gathering:
  https://arxiv.org/abs/2407.05879
- Causal Reinforcement Learning for Complex Card Games: A Magic The Gathering
  Benchmark: https://arxiv.org/abs/2605.06066
- AI solutions for drafting in Magic: the Gathering:
  https://arxiv.org/abs/2009.00655

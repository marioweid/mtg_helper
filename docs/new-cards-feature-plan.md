# New Cards for Your Deck — draft feature plan

## Now

The user authorized an **experimental application pilot**, narrowed to released, Commander-legal
cards. Implementation is on `feat/new-cards-pilot`; focused verification passed and independent
review found no blockers. See [verification](new-cards-pilot-checks.md) for limitations and the
[pilot contract](new-cards-pilot-contract.md) for the implemented scope. The broader
preview design below remains future work, not a claim about this pilot. Production is not deployed.
See the [initial measurements](research/new-cards-spike-2026-10-05/README.md),
[revised evaluator](research/new-cards-spike-2026-10-05/quality-v2-report.md), and
[controlled low/high reasoning comparison](research/new-cards-spike-2026-10-05/quality-v3-report.md).
The latest eight-call experiment used 19 previously unseen candidate identities plus 13 regression
cases on the same four synthetic physical decks. Both arms bound all 32 judgments correctly.
Arm-blinded review found 3 low-reasoning versus 2 high-reasoning error judgments; both still invented
Mirkwood Bats' toughness. High detected a real no-combo constraint violation, but only 2/4 high
responses passed all evidence checks versus 4/4 low, with median latency 93 versus 17 seconds.
Neither evaluator qualified as trusted recommendations. The authorized pilot therefore labels all
advice unverified, separates authoritative facts from prose, and conservatively excludes unresolved
release histories. It retains the deployed model and low reasoning; higher reasoning is not promoted.
All three separately authorized eight-call budgets are exhausted. No further paid benchmarks,
production database changes, or deployment are authorized by the implementation checks.

Confirmed user preferences:

- **Strong fits + Worth testing**, without filling either section with weak suggestions.
- Small changes are welcome: at most one or two supporting changes, not a major rebuild.
- **Current physical deck** is the assessment baseline; pending changes are not assumed complete.
- Planned additions are sufficient retention. No separate Saved list or recommendation archive.
- Start the 60-day clock at the main Commander-playable release; early promos must not shorten it.

The pilot uses explicit, cached eight-card analysis batches, durable account leases and daily quotas,
current physical context, source-quoted evidence, and guarded planned additions. It deliberately does
not claim complete candidate coverage or semantic correctness. Users can test the pilot and report
mistakes; trusted recommendations and preview eligibility still require further work.

## Goal

Add a New Cards tab to the deck detail view that answers:

> Which newly revealed or released cards are worth considering for this particular deck, and why?

This is a curated discovery feature, not a complete spoiler feed. It complements Top Picks:
Top Picks describes commander-level popularity; New Cards evaluates recent cards against the
actual decklist, strategy, and constraints. Empty results are preferable to weak filler.

## Proposed product behavior

- Include Scryfall previews until 60 days after the first main Commander-playable paper release.
  Early promos do not start this clock. Expire when the UTC date reaches that release + 60 days,
  even without a new sync. Preserve unresolved date/legality states instead of guessing.
- Separate release status from Commander legality. Prerelease legality and special products can
  differ from release dates. Never infer playable-now status solely from a date or Upcoming badge.
- Exclude reprints/alternate treatments of designs already available in eligible paper form.
  Include a first eligible paper appearance of a previously digital-only design; label that clearly.
  Old unbans and price drops are not new-card events. Deduplicate by Oracle identity.
- Derive the main playable release from print history and product eligibility, not the current
  representative printing or minimum paper date alone. Keep first-paper dates as separate evidence.
  Exclude tokens/playtest/acorn objects; later reprints do not reset the original playable window.
  Promo-only originals and delayed legality need explicit rules, not a blanket exclusion of promos.
- Do not treat first local import as proof of novelty. A reprint flag alone is also insufficient.
- An undated card with positive evidence of an upcoming eligible paper product remains Upcoming
  with date unknown until a date or withdrawal is known. This is an explicit expiry exception.
  Unknown-age imports without such evidence are unresolved, not automatically new. First-observed
  timestamps support diagnostics only; they do not establish historical release dates.
- Hide cards already in the deck or pending additions, matching by gameplay identity.
- Persist dismissals per owner/deck/Oracle identity; refreshes must not resurrect them.
- Expiry removes a recommendation from discovery, not its card record or planned addition.
- Reading the tab does not dismiss recommendations. A later unread badge is separate from expiry.
- No archive or Saved list in the MVP. Infrequent visitors can miss expired discoveries; this is
  accepted scope, not a promise to show everything since their last visit.
- Cancelling a planned addition makes it eligible again only while still recent and not dismissed.
  Dismissal is per deck, not an implicit dislike that trains recommendations across other decks.

### Recommendation presentation

Two sections, neither with a minimum item count:

- **Strong fits:** supported by the current physical list, a clear useful role or interaction,
  and no unresolved requirement for more additions. This is a reasoned recommendation, not proof
  of a strict upgrade or better win rate.
- **Worth testing:** a plausible sidegrade or conditional improvement. May require at most two
  additional supporting swaps, explicitly identified and justified using real card data. Support
  cards may be older; the headline discovery must be new. Larger rebuilds are out of scope.

Each item includes:

- Card image, preview/release status, separate legality status, and a Scryfall link.
- One or two concrete reasons, supporting card references/counts where useful, and a real caveat.
- Fit label separate from evidence confidence, not a probability or model confidence percentage.
- Optional replacement suggestion when defensible, with gains and losses rather than just a cut.
- Dependencies marked Already present, Planned, or Additional change needed. Missing dependencies
  prevent promotion to Strong fits. Unknown mechanics are not disguised as harmless speculation.
- Estimated price/ownership where available; unknown price is not zero. Do not infer numeric caps
  from words such as cheap. Unknown prices cannot be certified within an explicit hard budget.
- Plan addition and Dismiss actions, including undo. No automatic supporting swaps or mass Apply.

Label results as based on the physical deck. Pending cuts can threaten supporting interactions and
must be flagged. Separate suggestions are alternatives, not a jointly optimized upgrade bundle.
Planning one can affect the context of others. For incomplete decks, omit forced cuts and avoid
claiming that role deficits are problems in a finished 100-card list.

Reuse planned additions rather than directly altering the physical deck. Upcoming cards can be
planned but not silently completed as currently legal. Revalidate current eligibility, color
identity, and copy limits transactionally before physical completion, including single-plan and
batch revisions. Invalid selected changes must leave the plans and physical deck intact and return
an actionable error. Age expiry alone never blocks an otherwise valid planned addition.
Existing Rule 0/manual-deck behavior should not be broadened or silently overridden by this feature;
any shared completion-policy change needs explicit scope and regression coverage.
Show source freshness, analysis status, and actionable errors. Distinguish no matches from a
failed refresh. Retain usable cached results with an explicit stale indicator.

## Data-source research

### Scryfall: primary discovery and rules data

Official card objects expose Oracle identity, print identity, rules text, faces, color identity,
legalities, paper/digital availability, reprint status, release date, and optional preview metadata.
Bulk data updates every 12–24 hours. Use one daily shared sync, not external requests per deck.

The existing oracle_cards export contains one representative printing per Oracle ID, not a
first-printing history. Its released_at alone cannot establish novelty. Proposed ingestion streams
Default Cards to derive printing-history metadata while retaining only required history fields.
The spike found three early promos that would expire before main release if minimum paper date
were the clock. Normalize main playable release separately; the spike's date reducer is not the
production expiry algorithm.
This must not create a second writer racing the existing canonical-card sync. Coordinate discovery
and gameplay updates under one sync generation; publish only after successful validation.
Bootstrap history and backfill the active 60-day window before enabling results. New decks get that
same window, not only cards discovered after deck creation. A failed/partial feed must not expire or
withdraw records as if it were a complete snapshot. An empty feed warrants validation.

Persist complete face-aware rules and layout data for candidates AND existing commanders/deck cards;
backfill from Scryfall. Current ingestion only keeps top-level Oracle text. Keeping a face's text
is not enough: distinguish modal/transform/meld behavior instead of assuming every face is available
simultaneously. Preserve exact text for final evidence; current assistant briefings truncate text.

Preview discovery must not use the legal/banned-only importer gate. Keep preview eligibility
separate from current playability. Proposed gate: positive paper-product evidence, supported
layout, sufficient rules/identity data, no banned/acorn/playtest/token exclusions, and either
current Commander legality or confirmed future Commander eligibility for that paper product.
Unresolved cases remain pending verification, not asserted future-legal. Scryfall fields alone
may not establish that last condition; validate coverage with real previews and record
product exceptions from authoritative sources where necessary.

Preserve provenance, observation times, and meaningful content fingerprints. Handle corrected dates,
withdrawals, and Scryfall merge/delete migrations. Those migrations reference printing IDs: do not
assume every merge/delete changes or removes an Oracle identity. Retain tombstone/history
for user plans where appropriate rather than silently deleting user decisions.
Honor application headers, endpoint limits, caching, and 429 backoff. Daily freshness is the MVP;
intraday updates and completeness relative to every spoiler site are not promised.

Scryfall also publishes daily Oracle Tag bulk exports joined by oracle_id. These offer functional
roles without EDHREC access. Treat them as optional enrichment, never a candidate eligibility gate:
community tags can be missing, change, or be wrong, especially for previews. Use stable tag UUIDs,
not slugs, if integrated. Do not make another enrichment pipeline a prerequisite for shipping.

### EDHREC: optional only with authorized access

The published terms restrict automated searches/requests and reuse. Do not implement an
unauthorized scraper or depend on internal JSON endpoints. Link to EDHREC initially; seek
permission before integrating its statistics.

Its FAQ says deck data is collected daily and generally reflected within a few days. Statistics
are adoption evidence, not proof of improvement, and fresh previews have little history.
EDHREC also documents lift alongside historical synergy metrics; do not assume one universal score.
When using adoption statistics, denominators should reflect decks that could have included the card
since its preview, rather than counting older decks as negative evidence.

### Existing supporting sources

- Moxfield/Archidekt integrations: optional community evidence, subject to permitted access.
  Existing Top Picks describes a 28-day evidence cache, unsuitable as the discovery clock.
- Commander Spellbook: known combo completion evidence. Missing entries do not disprove new combos.
- MTGJSON: optional metadata cross-checking; its atomic model includes firstPrinting (a set code).
  No second discovery pipeline is required for the MVP.

## Proposed recommendation pipeline

1. **Discover independently of popularity.** Enumerate recent gameplay identities from local data.
   Do not seed the pool exclusively from community lists or popularity-limited searches.
2. **Filter eligibility.** Check combined commander/partner identity, paper eligibility,
   relevant legality, age, existing/planned copies, dismissals, and explicit constraints.
   Banned, digital-only, token, and inappropriate casual objects must not leak into recommendations.
   Validate previews separately: not_legal does not imply future Commander legality.
3. **Build deck context.** Use the commander(s), physical list, description, themes, role targets,
   curve, explicit account preferences, per-deck Coach memory, bracket, and protected cards.
   Pending additions are dependencies, not present support; pending cuts get explicit warnings.
   Structured current settings outrank inferred preferences; unresolved contradictory prose should
   produce a visible assumption, not an invented hard restriction. No cross-deck learning in MVP.
4. **Assess actual fit.** Evaluate support density, missing roles, mana requirements, setup,
   redundancy, and marginal value versus existing options. Distinguish triggers from replacements,
   cast from enter effects, token from nontoken conditions, and once-per-turn restrictions.
   A name/tag/word match is not proof. Known combo evidence includes prerequisites and resulting
   playstyle/bracket implications; infinite combos are not automatically desirable.
5. **Review candidates with bounded AI work.** Preserve a path for untagged cards, lands, generic
   role upgrades, and unknown archetypes. Proposed policy: process the recent eligible pool in
   bounded batches; heuristics prioritize but do not silently discard unknowns. If the run budget
   cannot cover it, report partial coverage and continue on an explicit request. Do not claim
   no strong matches while candidates remain unassessed. No vector embedding requirement.
   Deep-review a shortlist with exact rules and deck context. Require reasons, caveats, and optional
   replacement references; reject any/all candidates when appropriate. Support packages are bounded
   to two additional changes and must themselves respect deck constraints.
6. **Validate and cache.** Code validates IDs, referenced support counts, eligibility, and output
   shape; that does not prove the model's interpretation of Magic rules. Test semantic accuracy with
   curated fixtures and human judgments. Treat missing rules for a novel mechanic as unresolved
   rather than relying on model memory. No generated rule text may masquerade as source data.
   Cache both positive and negative assessments with evaluator/model/prompt and context versions.

Use deterministic eligibility checks and AI for contextual judgment, not an unrestricted
web-browsing agent or a complete Magic rules simulator. Do not invent score weights/confidence
percentages before calibration. Mechanical promise and community validation are distinct.
Neither EDHREC statistics nor community-tag coverage is required to reach Strong fits.

### Freshness, execution, and private-data contracts

- Opening a stale tab can request bounded background analysis; GET reads have no side effects.
  A refresh command checks the latest shared local catalog; it does not trigger an admin-wide sync.
  Show catalog last-success time separately from assessment time, coverage, and deck version.
- Fingerprint physical cards/quantities, commander rules, goals, Coach memory, preferences,
  and relevant pending changes. Do not rely only on decks.updated_at. Hash meaningful card content,
  not timestamps rewritten by every Scryfall upsert. Include new-candidate discovery generations.
- Compare input versions before publishing a job result. An older worker cannot overwrite newer
  analysis or represent results for a changed deck as current. Daily image/price-only updates should
  not rerun all AI analysis; reevaluate affected budget filters against current data.
- On every read/action, reapply expiry, legality, ownership, dismissed/planned/physical exclusions,
  and other deterministic constraints. Never display now-ineligible suggestions just because their
  cached explanation is recent. Date expiry does not require another paid analysis.
- Use a PostgreSQL claim/lease per owner/deck/context generation and durable result
  storage. Existing process-local job registries are insufficient for multi-worker deduplication.
  Bound request size, candidates, tokens, runtime, retries, and per-account concurrent work. Polling
  must not initiate jobs. Abandoned leases are recoverable and old attempts cannot publish.
  A crash after a provider call but before persistence can still duplicate cost; do not promise
  exactly-once billing. No new queue service is needed for this design.
- Authorize cached reads, refreshes, polling, dismiss/undo, and plan actions against the deck's
  owner. Shared catalog metadata may be global; deck context, explanations, collection data, and
  results are private and keyed by account/deck. Deck deletion removes private feature state.
- AI receives only needed card/deck/preference data, not account identifiers or full collection
  inventories. Treat external tags and free text as untrusted data, not instructions. No autonomous
  writes/web browsing; validate links and render explanations as safe text. Reuse usage accounting
  without logging raw private prompts. Existing disclosure of the AI provider must cover this use.
- External enrichment or AI failure leaves usable prior results marked stale/partial; a first-run
  failure is an error, not a successful empty list or unreviewed Strong fits.

### Recommendation evaluation before launch

Build a small labeled set across different decks, including two builds of the same commander.
Measure candidate coverage separately from final precision: a great final explanation cannot fix
an excellent card discarded upstream. Review false negatives as well as displayed suggestions.
Include real recent cards whose names are unfamiliar to the model. Shuffle candidate order and
repeat selected runs to detect unstable rankings/labels; LLM recommendation research documents
position bias, but its magnitude for this application is not yet measured.
Require no known legality violations or fabricated interaction claims in the reviewed Strong fits
set. Establish usefulness thresholds with user judgments, not model self-ratings. Record cost,
latency, number assessed, and partial/error rates. A bounded dry run must establish actual run
budgets and coverage before the job settings are finalized.

## Existing integration points and limitations

- `frontend/app/decks/[id]/page.tsx`: Cards, Top Picks, Combos, and History tabs.
- `frontend/components/top-picks-panel.tsx`: source status and planned-addition patterns.
- `backend/src/mtg_helper/services/scryfall.py`: bulk importer and canonical selection.
  Currently persists released_at but not preview/reprint/first-release metadata. Import eligibility
  accepts Commander legal/banned cards; verify preview coverage rather than broadly relaxing it.
- `backend/src/mtg_helper/services/deck_fit_service.py`: explainable deck-relative evidence,
  but community-backed base scores disadvantage unseen cards if reused unchanged.
- `backend/src/mtg_helper/services/commander_coach/synergy_scoring.py`: candidate scoring,
  but specialized packages cover only some themes, candidate discovery favors popularity,
  and the existing discovery path excludes lands. Do not inherit those limitations for New Cards.
- `backend/src/mtg_helper/services/planned_change_service.py`: owner-scoped planned additions.
  The live completion route delegates to `services/revision_service.py`, whose application path
  does not revalidate legality. Cover both single completion and batch revisions.
- `backend/src/mtg_helper/services/assistant_deck_context.py`: briefing/inspection patterns,
  but briefings truncate Oracle text and need face-aware source data before semantic claims.
- `backend/src/mtg_helper/services/bracket_service.py`: existing bracket evidence, with name-based
  catalogs that cannot automatically classify novel spoilers. Verify policy against current Wizards
  guidance; bracket preferences are not synonymous with Commander legality or guaranteed power.
- `backend/src/mtg_helper/services/commander_coach/jobs.py` and `services/optimizer_jobs.py`:
  process-local jobs; reuse progress conventions, not their durability assumptions.
- `backend/src/mtg_helper/services/combo_service.py`: existing Commander Spellbook integration.
- `OPERATIONS.md`: production card sync is currently weekly; local sync is manual.

Likely new responsibilities: shared release metadata, a deck-specific assessment service/cache,
owner-scoped dismissal state, and a New Cards panel. Exact schema and API contracts remain open.
Reuse PostgreSQL and existing job mechanisms where suitable; no new infrastructure by default.

## Implementation sequence

1. **Data feasibility spike:** verify preview coverage, first-eligible-paper dating, product
   exceptions, and face-aware backfill against real Scryfall records. Do not broaden existing
   legality filters globally to make a demo work. Measure import cost before choosing the sync path.
2. **Quality/cost spike:** assess a recent pool against curated decks. Measure coverage, semantic
   accuracy, runtime, tokens, and sensitivity to candidate order. Set bounded run budgets.
3. Finalize assessment, job-claim, and dismissal schema/API contracts from spike results.
   Implement daily discovery, owner checks, invalidation, and regression-tested completion guards.
4. Add the tab, status/coverage states, dismissals, and planned additions. No automatic deck edits.
5. Add Oracle Tags or authorized community statistics only if they improve measured quality.

The initial spikes ran; results are linked under Now. They established data availability and low
per-batch cost, but did not resolve recommendation correctness, full-pool recall, or playable-release
normalization. Complete a focused follow-up before declaring these implementation gates passed.

## Acceptance checks

- An old card's reprint or changed canonical printing never becomes newly released.
- Historical bootstrap does not flood the feed with old cards.
- Dated previews survive through main playable release and expire 60 days later, using UTC dates.
  Early promos cannot cause expiry before that release; ordinary later reprints cannot reset age.
- Verified undated previews follow the explicit exception; unknown-age imports do not become new.
- First eligible paper appearances can qualify despite prior digital existence; old paper reprints,
  unbans, and price drops do not. Ineligible earlier printings do not set the window.
- Missing/corrected dates, release/legality disagreements, withdrawals, and migration merges/deletes
  have tested behavior. Partial/failed syncs cannot masquerade as successful deletions.
- Double-faced cards and commander/partner color identities are evaluated correctly.
- Banned/otherwise ineligible cards are excluded. Cards awaiting verified future Commander legality
  may remain preview-only even if physically released; never mislabel them currently playable.
- A mechanically strong card can qualify with no EDHREC rank or community observations.
- Same commander with different strategies/support densities yields different recommendations.
- Explanations reference real interactions; replacement suggestions preserve required roles and
  protected cards. No unsubstantiated combo or win-rate claims.
- Face-aware backfill supplies complete rules for both new cards and existing deck support.
- Strong fits need no supporting additions outside the physical deck; Worth testing allows at most
  two supporting changes. Pending changes never count silently as physical support.
- Planned/in-deck cards are excluded by Oracle identity, including alternate printings. Cancelled
  plans resurface only if still eligible. Expiry preserves plans without creating an archive.
- Single and batch completion revalidate eligibility atomically and preserve plans on rejection.
- Dismissals survive syncs/rescoring/print changes and stay local to this deck; undo works.
- All private read/write/job endpoints reject cross-owner access, including cache hits and polling.
- Meaningful deck changes invalidate results even without a timestamp change. Newly discovered
  candidates trigger assessment; expiry without sync hides cards. Old workers cannot publish as new.
- Simultaneous refreshes share work across processes; abandoned claims recover. Token/runtime/retry
  bounds are tested, and restart-related duplicate provider cost is acknowledged rather than hidden.
- Source failures and budget-limited coverage show stale/partial status, not an empty success.
- Candidate-order permutations, unfamiliar mechanics, unsupported archetypes, and missing tags are
  covered in evaluation; high scoring and polished prose alone are not quality evidence.
- A small curated evaluation set includes obvious matches, thematic traps, generic staples,
  unsupported build-arounds, lands, and unknown-data spoilers. Review precision and missed strong
  candidates before choosing thresholds; collect user judgments rather than claiming measured
  accuracy without evaluations.

## Remaining decisions and scope

Product preferences needed for the current draft have been answered. Recommended defaults are:
respect explicit avoid/pet-card and target-bracket preferences, do not assume maximum power is the
user's goal, and show unknown price rather than inventing a cap. Hard versus advisory handling of
ambiguous prose remains an implementation contract, with visible assumptions as the safe fallback.

Technical blockers to close with evidence: positive preview eligibility across product types,
face-aware history/backfill, safe completion integration, candidate coverage within a measured run
budget, and private generation-checked job publication. No schema/API is frozen by this draft.

Reprints/price alerts, a Saved list/archive, cross-deck dashboards, notifications, major rebuilds,
projected-deck comparison, autonomous swaps, and exhaustive spoiler browsing remain out of scope.

### Challenge outcome

The direction survives review, but the original plan understated data work and overstated how much
existing scoring/jobs could be reused. The main quality risk is false confidence from plausible
text; the main coverage risk is rejecting unrecognized mechanics before assessment. Neither is
solved just by choosing a larger model. Keep the MVP focused, establish evidence first, and avoid
adding more community integrations until the base recommendations work.

## Sources

Official documentation and supporting research consulted during planning:

- https://scryfall.com/docs/api/cards
- https://scryfall.com/docs/api/bulk-data
- https://scryfall.com/docs/api
- https://scryfall.com/docs/api/rate-limits
- https://scryfall.com/docs/api/cards/manifest
- https://edhrec.com/faq
- https://edhrec.com/terms
- https://edhrec.com/articles/from-synergy-to-lift-the-math-behind-edhrecs-new-era
- https://mtgjson.com/data-models/card/card-atomic/
- https://spacecowmedia.github.io/commander-spellbook-backend/
- https://scryfall.com/docs/syntax
- https://scryfall.com/docs/api/cards/search
- https://scryfall.com/docs/api/tags
- https://scryfall.com/docs/api/migrations
- https://wpn.wizards.com/en/news/format-legality-shifts-prerelease-one
- https://magic.wizards.com/en/news/feature/whats-inside-mystery-booster-commander-edition
- https://magic.wizards.com/en/news/announcements/commander-brackets-beta-update-february-9-2026
- https://arxiv.org/html/2508.02020v1
  (Research preprint on recommendation position bias; not a measured result for this application.)

A read-only live Scryfall query for `game:paper date>now not:reprint` returned upcoming paper cards
with Commander `not_legal`, confirming an importer preview-coverage gap. One sampled
product's official Wizards page specifies a separate Commander legality date, reinforcing that
release date alone is not a legality rule. This was a sample, not a complete product-coverage audit.
Scryfall search supported this probe; not:reprint is not the production novelty algorithm.

Source capabilities and terms must be rechecked at implementation. Subsequent feasibility work
scanned complete public exports and made eight bounded model calls; findings, costs, test results,
and limitations are in [the spike report](research/new-cards-spike-2026-10-05/README.md).
No production ingestion, database migration, deployed job, or actual deck mutation was performed.

# Local-first discovery: discussion options

Research date: October 28, 2026. This is a brainstorm, not an approved implementation spec.
No application, database, provider permission, or paid-model changes were made for this note.

## Recommendation

Make the default discovery experience a local catalog query. Use Scryfall Oracle tags and card
facts to find candidates; add community evidence only as optional, separately attributed ranking
evidence. Keep AI in an explicitly requested chat/explanation workflow, not on the card-loading path.

The important guarantee is not that a third party will stay online forever. It is that losing one
optional source does not remove the product's core discovery capability. Local retention must still
follow each source's permission and deletion requirements; caching does not create reuse rights.

See [community-data research](discovery-data-sustainability.md) for external provider findings.

## What the current repository actually does

These are code observations, not measurements of the running application:

| Area | Current behavior | Implication |
| --- | --- | --- |
| Experimental Discover | Planning, revision, then review; a separate optional strategy draft | Several dependent AI calls before assessed recommendations exist |
| Strategy draft | Three free-text directions; selecting one populates the editable goal | Reusable strategy-to-tag queries would be a new behavior, not something already implemented |
| Discover browsing | Local source browsing, explicitly separate from generation | Existing model-free browsing is a useful foundation, but not a default curated feed |
| Top Picks | Fetches/refreshed provider data during the request when caches need it | Removing AI alone does not remove external waiting |
| Moxfield recommendations | Top ten liked decks, cached for 28 days; browser TLS impersonation | Not a representative population or a stable, documented access contract |
| Archidekt recommendations | Extracts deck links from search-page HTML, then fetches up to twenty matching decks | HTML layout and network availability affect the refresh |
| New Cards | Read-only local card/tag query; commander tags include descendants | Reusable source-backed approach, not AI |
| New Cards freshness | Sources older than two days stop returning matches | Do not copy this policy into a long-term outage fallback without an explicit decision |
| Card catalog | Already stores `edhrec_rank` | A global popularity field already exists; it is not commander-specific synergy |

Implementation references:

- [Discover workflow](../../backend/src/mtg_helper/services/recommendations/pipeline.py)
- [Discover orchestration](../../backend/src/mtg_helper/services/recommendations/service.py)
- [Current strategy draft](../../backend/src/mtg_helper/services/recommendations/strategy.py)
- [Discover screen](../../frontend/components/discover-panel.tsx)
- [Top Picks](../../backend/src/mtg_helper/services/top_picks_service.py)
- [Moxfield fetch/cache](../../backend/src/mtg_helper/services/moxfield_recs_service.py)
- [Archidekt fetch/cache](../../backend/src/mtg_helper/services/archidekt_commander_recs_service.py)
- [New Cards reads](../../backend/src/mtg_helper/services/new_cards/service.py)
- [New Cards matching/freshness](../../backend/src/mtg_helper/services/new_cards/repository.py)
- [Catalog schema](../../backend/src/mtg_helper/sql/schema.sql)

## Tags are an appropriate foundation, but not a complete recommendation engine

Scryfall officially provides daily Oracle-tag bulk exports. It describes Oracle tags as functional
roles and documents joining them to card facts by `oracle_id`. Tags are community-maintained;
Scryfall explicitly warns that errors and abuse remain possible. Use stable tag UUIDs, not slugs.
Sources: [bulk exports](https://scryfall.com/docs/api/bulk-data),
[tag object and cautions](https://scryfall.com/docs/api/tags).

That is a supported distribution mechanism, unlike discovering an internal endpoint. It is still
not an uptime guarantee or an irrevocable license: Scryfall's
[terms](https://scryfall.com/docs/terms) reserve the ability to restrict/change services.

The repo's [earlier coverage study](scryfall-tag-coverage/README.md) found at least one tag on 99.36%
of its eligible Commander nonlands in an October 12 snapshot. This is historical any-tag coverage,
not today's count, relevant-tag coverage, or measured recommendation accuracy.

Simply removing New Cards' release-date condition would produce an all-age tag-match browser. It
would not automatically produce a good discovery feed:

- Many tags describe cycles or other incidental facts, not the selected strategy.
- Common ramp/draw labels can drown out more distinctive matches.
- Overlapping tags do not prove rules compatibility or contextual usefulness.
- Complementary cards may have different tags: a token payoff need not create tokens itself.
- New/untagged cards must remain reachable through name, printed keywords, and literal searches.
- A commander can support several strategies; a broad overlap score cannot know the user's choice.

Use editable source-tag filters, intersections/unions, and transparent match explanations. Avoid
creating another permanent locally invented card-label system or a hand-maintained tag-to-strategy
ontology. Optional AI can help translate intent into a saved source query, but initial browsing must
work before that assistance and without it.

## A possible user experience

User direction during this research: retain a strategy the user can describe or explicitly generate
for the commander, associate that strategy with the tags it aims for, and reuse the same strategy
later in deck-agent chat. Compare both free and permissioned/paid community-data options before
choosing. This is product direction for further discussion, not approval of an interface or schema.

Opening Discover immediately shows local candidates, with no model or community-network requests.
New Cards can remain a recent-release lens over shared source facts; it need not share every ranking
or freshness rule with all-card discovery.

A strategy could retain human-readable intent plus editable, validated source-tag queries. Generation
is an explicit setup/refinement action, not something repeated on tab entry, pagination, filtering,
or every deck change. If no strategy exists yet, offer manual source-tag selection and basic local
browsing while an optional draft runs. Do not make the first visit wait for an AI draft either.
Save prose independently from queries: some strategic intent will not be expressible using tags.
Represent complementary search lanes rather than requiring every candidate to share every strategy
tag. A model may suggest existing tag IDs; it must not invent or permanently assign card labels.
If an upstream tag is removed, preserve strategy prose and ask for query review rather than silently
substituting a different label. These are proposed behaviors to validate, not a chosen data model.

For example, a creature-recursion strategy could have separate searches for sacrifice outlets,
creature recursion, and death-triggered draw. These are descriptions of the strategy's queries,
not new global card labels. Requiring every candidate to satisfy all three would discard many of
the complementary pieces the strategy actually wants.

Possible result groups, to discuss rather than commit to:

1. **Matching your focus:** selected source tags and filters, with actual matching labels visible.
2. **Popular options:** matching cards with a modest popularity preference; global rank clearly
   distinguished from commander-specific deck inclusion.
3. **Explore:** less-played and recently released matches, so popularity is not an admission gate.

Show concise evidence such as “Matches selected tag: sacrifice outlet” or “In 8 of 20 sampled decks
from source X; refreshed on date Y.” Do not turn either statement into “proven synergy.”

An optional “Ask about this card” action can open chat using the current commander, chosen strategy,
card facts, and optionally the actual deck if the user wants deck-aware advice. AI failure should
not remove the card results or prevent manual planning.

## Ranking principles before choosing weights

- Apply legality, combined commander color identity, exclusions, and explicit user constraints first.
- Rank primarily by selected focus; favor informative functional matches over generic overlaps.
- Scryfall's tagging weight describes how prominently a tag applies to a card, not its strength in
  this commander strategy. Keep any use of that field distinct from contextual relevance.
- Start simply: source-tag matching with global popularity as a bounded secondary preference or
  tie-breaker. Test against tag-only and popularity-only baselines before adding complex scoring.
- Keep a discovery route for cards with no popularity data. Missing evidence is unknown, not bad.
- Commander-specific inclusion, if legitimately available, is more targeted than global popularity.
  Compare against an eligible color/strategy baseline before calling an association “synergy.”
- Report sample sizes and dampen tiny samples. Ten highly liked decks are not the whole community.
- Deduplicate copied decks, precon mirrors, and cross-site duplicates before combining populations.
- Do not assume two sites are independent confirmations when the same decks appear on both.
- Treat a user's dismissal as deck-local unless they explicitly choose otherwise. Do not train a
  shared community signal from private decks or actions without clear consent.

No numeric score weights are justified yet. Evaluate on varied, previously unused commanders and
strategies with human relevance judgments, including complementary enablers, new cards, budget
options, broad-tag noise, and rules false positives. Measure first-result latency separately from
ranking quality. A sub-second warm local response is a proposed target, not a measured result.

## Reliability and permission design

The useful seam is between **local discovery reads** and **background source ingestion**. The
discovery module should hide eligibility, source consistency, ranking, pagination, and provenance
behind a small interface. Provider-specific adapters belong on the ingestion side, not inside the
page-load implementation. Reuse existing catalog/publication machinery instead of building a new
provider framework in anticipation of integrations that may never be authorized.

The current experimental browser also requires a rules snapshot and rejects partner commanders.
Those are current pilot constraints, not inherent limitations of local tag discovery. A future
default card browser should not stop working merely because an AI/rules dependency is unavailable;
support for combined commander identities still needs explicit acceptance checks.

For sources actually adopted:

- Save source identity, update time, schema/version, coverage, and relevant permission evidence.
- Refresh in background with documented limits and truthful health/freshness status.
- Validate a complete replacement before publishing; failed refreshes do not mean zero matches.
- Keep last-good snapshots only for as long and for the uses that source permits.
- Distinguish temporarily unavailable access from permission revocation or required deletion. The
  latter may require purging even previously cached data and derived evidence.
- If community evidence disappears, remove its boost and label the change; local tag discovery stays.
- If card/tag updates disappear, explicitly show snapshot age and that legality/current coverage may
  be outdated. Decide separately when stale results remain browseable versus blocked for actions.
- Provenance makes it possible to remove one revoked source without losing unrelated evidence.

## Decisions to discuss with the user

1. Direction received: commander strategy, described or explicitly generated, connected to source
   tags and reusable in chat. Still clarify whether future deck-aware ranking is needed; do not
   silently make the current commander-only pilot deck-aware.
2. Direction received: compare free and permissioned/paid sources first. No spending or contact is
   authorized. Exact EDHREC-style commander recommendations require a much richer signal than
   global popularity alone.
3. Should community information only reorder locally found matches, or also supply a clearly marked
   secondary candidate lane? The latter finds complementary cards tags may miss, but needs access.

Suggested sequence: agree on local-first behavior; prototype tag/focus ranking offline; compare
quality and latency; pursue provider permission in parallel; only then specify and approve changes.
No provider contact, paid call, production migration, or implementation is authorized by this note.

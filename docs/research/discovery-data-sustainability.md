# Sustainable community data for discovery

## Now

**Research checkpoint: 2026-10-28. No implementation is approved by this note.**

There are legitimate ways to use community signals without making every Discover request wait for
an LLM or a fragile website fetch. However, **an unrestricted, large, current Commander deck corpus
with verified upstream reuse rights was not found in this investigation**.

The practical distinction is:

- **Scryfall:** documented API and bulk exports, explicit permission for additional Magic software,
  local caching encouraged, and an official `edhrec_rank` field. Strongest immediately documented
  access path for a **global popularity prior**, not commander-specific recommendations.
- **Commander Spellbook:** official API and bulk combo export explicitly intended for third-party
  consumption. Good specialized interaction source. The MIT statement explicitly covers source
  code; do not present the complete production database as MIT-licensed without clarification.
- **Archidekt:** developers publicly welcome API reads, but published terms contain conflicting
  automation/noncommercial restrictions. Best initial permission conversation, not a clean open-data
  license today.
- **Moxfield and EDHREC:** published restrictions make unapproved sustained ingestion unsuitable.
  Ask for written access **and** reuse/retention permission, preferably an aggregate or bulk feed.
- **MTGJSON:** useful offline distribution with an MIT license statement, but third-party rights are
  expressly reserved. It does not independently solve licensing of underlying EDHREC signals.
- **Actually licensed examples exist:** 17Lands public datasets are explicitly CC BY 4.0, but concern
  Limited, not Commander. One creator's explicitly CC BY 4.0 Commander lists were verified; that is
  a possible seed/example source, not representative community popularity.

These are source/policy findings, not legal advice or a measured speed/quality result. No app,
database, paid model call, provider account, bulk corpus ingestion, or permission outreach was run.

## What was verified, and what was not

**Verified** means a first-party document, service response, or maintainer statement was inspected.
**Not found** means this bounded search did not locate a grant or contract; it does not prove one
cannot exist. **Inference/recommendation** means our interpretation, not a provider promise.

Sources were inspected on 2026-10-28. Most live documentation has no visible effective date. Dates
below are dates actually displayed, not dates inferred from search-engine freshness. In particular,
Archidekt forum ages are relative labels; they are not converted into invented publication dates.

Keep these four questions separate:

1. **Access:** Is this supported API/export intended for this application and use volume?
2. **Reuse:** May we store, transform, display, redistribute, or commercially use these fields?
3. **Retention:** What must be refreshed/deleted, and what survives revocation or deck privatization?
4. **Underlying rights:** Does the grant cover user text, source decks, third-party statistics, card
   text/art, and database rights, or just the provider's software?

A successful HTTP response, an export button, a third-party SDK's MIT license, a research paper, or
an uploaded dataset's license label does not answer all four. A license a user gives a hosting site
is not automatically a license to MTG Helper. Nor does reducing data to aggregates automatically
erase contractual restrictions on obtaining or using it.

The robots standard itself says: **“These rules are not a form of access authorization.”**
[RFC 9309 §1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1), published September 2022.
Honor robots restrictions, but do not treat an allowed path as a content license or terms override.

## Moxfield: permission-gated, not a public API dependency

### Access evidence

- The first-party [API root](https://api2.moxfield.com/) says:
  **“This API is not intended for public use.”** It points to the
  [current API FAQ](https://moxfield.com/help/help-articles/faq#moxfield-api).
- The FAQ HTTP fetch returned a JavaScript loading shell, so its substantive API policy was **not
  verified**. The old `/help/faq` rendered an application 404. Neither observation proves Cloudflare
  blocked the request; do not report a block that was not observed.
- [Terms](https://moxfield.com/help/terms), **effective July 9, 2026**, §4(c), restrict automated access
  except as **“expressly approved by Moxfield.”** Ordinary access is personal/noncommercial;
  competitors require prior written consent.

### Reuse and retention evidence

The same terms, §5, say:

> Systematic retrieval of data ... to create or compile ... a collection, compilation, database or
> directory without written permission from Moxfield is prohibited.

Ellipses omit intervening text, not a claimed exception. Section 7 says user-posted content
**“belongs to you”** and grants rights to Moxfield. This is not a blanket downstream reuse grant.

**Not found:** a public supported API contract, open-data license, numeric quota, standard approved
client authentication, cache TTL, deletion propagation contract, or rights to retain derived
commander/card counts after access ends. Those are questions for an agreement, not defaults to guess.

**Permission path:** `support@moxfield.com`, published in §17. Ask whether recommendation/discovery
is considered a competing use and whether permission for user-requested imports differs from
systematic search/indexing. API whitelisting alone is insufficient if persistent reuse remains banned.

## Archidekt: welcoming API statements, unresolved terms conflict

Correct spelling: **Archidekt**, not Archideck or Archidect.

### Access evidence

First-party forum statements by developer `michael` are useful evidence of intent:

- [“API To Query Deck”](https://archidekt.com/forum/thread/40353/1), displayed as **“7 years”**:
  **“our API is open and public (as far as reading is concerned)”**. It asks that consumers
  **“link back to Archidekt”**, credit individual brews, notes the lack of maintained documentation,
  and warns that harmful volume could lead to API lockdown.
- [“No API”](https://archidekt.com/forum/thread/2832338), displayed as **“4 years”**:
  **“You're more than welcome to use our API for whatever you want”**, followed by a warning that
  **“you might hit our rate limiter if you hit it too hard.”** No numeric quota is supplied.
- [“API querying”](https://archidekt.com/forum/thread/16962481), displayed as **“12 months”**,
  contains further developer API guidance. This supports ongoing engagement, not version stability.
- [“API deck count above 1000”](https://archidekt.com/forum/thread/15498179), displayed as
  **“14 months”**, explains count removal because expensive queries could
  **“slow the site down to a crawl for everyone else.”** A useful warning against treating public
  discovery/search as an unlimited bulk-download service.

### Reuse and retention evidence

The published [terms](https://archidekt.com/terms), **effective September 07, 2018**, nevertheless
limit access to **“solely for your own personal, noncommercial use”**, restrict copying,
distribution and competing websites, and prohibit scripts producing **“automated searches,
requests, or queries.”**

**Inference:** developer encouragement is stronger than discovering an undocumented endpoint, but
does not resolve that conflict for a competing/commercial service or establish rights over every
user's deck description. Do not silently choose the most permissive sentence.

**Not found:** a versioned official API specification, numeric request quota, comprehensive dataset
license, standard bulk-discovery grant, cache/retention policy, or downstream deletion agreement.

**Permission path:** `contact@archidekt.com`. The official
[contact page](https://archidekt.com/contact) invites **“business inquiries.”** Request a written
exception/clarification covering this actual use, including whether reading a named public deck and
indexing thousands of decks are treated differently.

## EDHREC: seek an aggregate feed/partnership

### Access and reuse evidence

[Terms](https://edhrec.com/terms), **effective August 06, 2024**, grant ordinary use
**“solely for your own personal, noncommercial use.”** Section 2 restricts copying, redistribution
and building similar/competitive websites. Section 3 prohibits automated agents/scripts generating
**“automated searches, requests, or queries to the Site”** and gathering information about other
users without consent.

**Not found:** an official public, supported API specification or an open-data grant covering
commander-specific inclusion rates, synergy scores, raw decks, or bulk statistics. This does not
assert that EDHREC has no internal API or cannot issue partner access. Public JSON used by its own
frontend and third-party wrappers are not a verified public API contract.

The [About / Data Partners page](https://edhrec.com/about-us) says **“EDHREC pulls decklists from”**
Archidekt and Moxfield. That verifies EDHREC's stated sourcing. It does **not** transfer EDHREC's
partner permissions to MTG Helper, nor establish that all source deck content is openly licensed.

**Retention gap:** no verified standard grant for snapshot history, republishing derived statistics,
deletion/private-deck handling, or keeping derived artifacts after termination.

**Permission path:** `contact@edhrec.com`, on the fetched
[contact page](https://edhrec.com/contact-us). Prefer it to inconsistent older search snippets.
Ask for a limited, attributed commander-to-card aggregate feed rather than a raw deck mirror.
Willingness, availability, cost, quota and commercial/AI rights remain unconfirmed.

## Robots snapshots: operational signals, not reuse licenses

First-party files inspected on 2026-10-28; no numeric crawl delay was shown in these three:

| Host | Relevant snapshot |
| --- | --- |
| [Moxfield](https://moxfield.com/robots.txt) | Disallows `/user/admin.html`, `/search/*`, `/account/*`, `/collection/*`, `/binders/*`. |
| [Archidekt](https://archidekt.com/robots.txt) | Disallows `/login?`, `/partialCompare`, `/playtester-v2/`, `/sandbox?`. |
| [EDHREC](https://edhrec.com/robots.txt) | Disallows article embeds/previews and `/deckpreview/`. |

These snapshots do not establish rules on every API subdomain. Recheck the actual authorized host
and provider agreement before access. No protection bypass, proxy rotation, challenge solving,
browser impersonation, or protected deck-endpoint scraping was attempted or recommended.

## Scryfall: official bulk popularity, with meaningful limits

### What is explicitly offered

The [API documentation](https://scryfall.com/docs/api) describes a REST-like API for programmatic
ingestion and provides data free of charge for **“creating additional Magic software, performing
research, or creating community content.”** This is affirmative service-use guidance, not merely
an accidentally reachable endpoint.

The official [card object](https://scryfall.com/docs/api/cards) defines nullable `edhrec_rank` as:

> This card's overall rank/popularity on EDHREC. Not all cards are ranked.

The official [search documentation](https://scryfall.com/docs/api/cards/search) also supports
`order=edhrec`, lowest rank first. [Bulk documentation](https://scryfall.com/docs/api/bulk-data)
provides daily exports including Oracle Cards, one card object per Oracle ID. The inspected page
showed Oracle Cards updated **2026-10-28 09:02 UTC**. It currently documents gzipped JSONL and
`jsonl_download_uri`; do not assume historical JSON-array examples describe today's format.
No bulk file was downloaded to verify every individual record.

### Access and retention rules

[Rate-limit documentation](https://scryfall.com/docs/api/rate-limits) explicitly encourages local
processing/caching **“at least for 24 hours”** and requires bulk files for rapid large-scale card
lookups. **This is not a 24-hour maximum retention rule.** No fixed maximum cache lifetime was found
in the inspected API rules. It is also not an irrevocable right to republish all historic data.

Current documented limits differ by endpoint: `/cards/search`, `/cards/named`, `/cards/random`,
and `/cards/collection` are **2/second**; `/cards/manifest` is **10/minute**; other methods are
**10/second**. API calls require accurate `User-Agent` and `Accept` headers. Respect 429s; repeated
overload can lead to a ban. Bulk exports are the intended mechanism for local indexing, not crawling
all search pages.

### Reuse scope and limits

The API rules prohibit paywalling Scryfall data, implying Scryfall endorsement, and simply
repackaging, republishing or proxying the data: **“Your software must create additional value for
end-users.”** Card imagery has additional attribution/non-alteration rules. The
[terms](https://scryfall.com/docs/terms) reserve the ability to change/restrict services; this is not
an uptime guarantee or a CC-style irrevocable database license.

**Supported conclusion:** using the supplied rank field inside value-adding Magic software has a
much stronger documented access/use basis than collecting EDHREC's website endpoints.
**Not established:** a separate, portable, unconditional license to EDHREC's whole database,
commander-specific recommendations, or redistribution of an extracted rank archive. No rank-specific
upstream sublicense, refresh SLA, or independent EDHREC license was found in Scryfall's inspected
documentation. Ask Scryfall about any planned use outside normal documented consumption, especially
paid products, redistributed datasets, historical archives or AI training.

**Quality limitation/inference:** overall popularity can favor universal staples. It supplies
neither commander-conditioned inclusion rates nor evidence that a card supports the user's specific
plan. Missing ranks must not exclude cards; a new or niche card can be useful before it is popular.
Do not describe a global prior as “EDHREC synergy.”

**Contact path:** the documentation links [Contact Us](https://scryfall.com/contact), but that page
returned HTTP 403 during this research. The API and terms pages themselves were readable. Do not
work around the 403; a person can use the normal official contact route. Scryfall's terms disallow
posting synthesized content **on Scryfall**; that sentence alone does not establish a blanket ban on
all off-site AI use, nor an affirmative license for model training.

## MTGJSON: offline-friendly, not an upstream-rights reset

Verified first-party evidence:

- The [homepage](https://mtgjson.com/) describes aggregation from multiple resources and
  **“approved partners”**, daily builds, and downloadable JSON/CSV/database formats.
- The [license page](https://mtgjson.com/license/) applies an MIT license statement to its website
  and content; the [FAQ](https://mtgjson.com/faq/) calls MTGJSON free/open source under MIT and
  recommends compressed downloads for local use.
- The [Atomic Card model](https://mtgjson.com/data-models/card/card-atomic/) includes optional
  `edhrecRank` (**“The card rank on EDHRec”**) and `edhrecSaltiness`.
- Its [own provider source, pinned to inspected commit
  `9561e5aaeb95bfb877eea9c3f8b0997ab7a95a72`](https://github.com/mtgjson/mtgjson/blob/9561e5aaeb95bfb877eea9c3f8b0997ab7a95a72/mtgjson5/providers/salt.py)
  explicitly maps EDHREC's `rank` and `salt` to those fields. This verifies provenance, not an
  invitation for us to call that upstream URL; it was not probed here.
- Crucially, the homepage footer says **“Third-Party content, links and referrals ... is subject to
  their own terms, rights and other legal notices.”**

**Interpretation:** MIT is affirmative permission for material MTGJSON can license; it must not be
represented as relicensing all Wizards IP, EDHREC statistics, prices, or user decks regardless of
upstream terms. A general “approved partners” statement is not the specific downstream sublicense
for every field. Ask which third-party fields may be stored, used commercially and redistributed,
and under what notices/retention limits. Preserve the MIT notice for covered material.

The [deck model](https://mtgjson.com/data-models/deck/) includes product set code, release date and
sealed-product references; [All Decks](https://mtgjson.com/downloads/all-decks/) is a downloadable
deck catalog. Those documents do not establish a representative community Commander corpus.
Do not confuse packaged/product decks with current community popularity.

**Permission path:** [MTGJSON Discord](https://mtgjson.com/discord), explicitly recommended in its
FAQ for data-source questions. MTGJSON can be operationally useful, but the documented overall rank
still does not supply commander-conditioned inclusion or synergy. Saltiness is a separate signal,
not a substitute for those missing relationships.

## Commander Spellbook: supported interaction data, clarify database rights

The official [About page](https://commanderspellbook.com/about/) links its REST backend and says:

> The source code for the website and the backend server are completely free and open source under
> the MIT license.

Notice the scope: **source code**, not an explicit CC/MIT declaration for every production record.
The [backend license](https://github.com/SpaceCowMedia/commander-spellbook-backend/blob/master/LICENSE)
is conventional MIT text for software/documentation.

### Access and local processing are expressly documented

The live [API root](https://backend.commanderspellbook.com/) was readable and publishes usage
guidelines. Official [API & Clients documentation](https://spacecowmedia.github.io/commander-spellbook-backend/api.html)
lists search, `find-my-combos`, bracket estimation and generated clients. Its bulk section says:

> Do not use the HTTP API to export the whole dataset.

It instead explicitly publishes
[`variants.json.gz`](https://json.commanderspellbook.com/variants.json.gz) and an uncompressed JSON
alternative, refreshed periodically, with `timestamp`, `version`, `variants` and `aliases`:
**“Fetch it on a schedule of your own and read it locally.”** The documentation displays
**October 19, 2026** and **July 11, 2026** timestamps. No full export was downloaded here.

API guidance is sparse unauthenticated requests, a few calls per user interaction, identify the
service in `User-Agent`, **80 requests/minute should be safe**, handle 429/backoff, and credit/link
back to Commander Spellbook. “Should be safe” is guidance, not a guaranteed capacity reservation.

### Remaining rights and data-scope questions

This is a legitimate third-party-use path with affirmative local-copy guidance. However, an explicit
production **data license**, commercial redistribution grant, maximum retention/deletion policy and
AI-training grant were not found. Request clarification before claiming a freely relicensable mirror
of combo prose, votes, prices and popularity fields.

In particular, the [official syntax guide](https://commanderspellbook.com/syntax-guide/#popularity)
says combo popularity is **“the number of decks containing the combo”** among **EDHREC decklists**.
Spellbook popularity is therefore not evidence of an independent openly licensed deck corpus.
Ask separately about EDHREC-derived `decks`/popularity fields, editorial steps/prerequisites,
Scryfall fields, third-party prices and user-contributed material. Its own salt voting is a different
signal from EDHREC card saltiness.

**Tradeoff:** curated multi-card interactions can improve combo discovery, but are not general
commander-specific staple recommendations. Requirements, starting zones, mana and desired bracket
must be respected; avoid recommending unwanted infinites just because they exist in the export.

**Permission path:** the About page links the
[official Discord](https://discord.com/invite/DkAyVJG) and asks developers to invoke `@Artificers`.
Do not use its deck-URL parsing endpoint as a proxy around another provider's restrictions.

## Open deck datasets: verified examples and limits

### 17Lands public datasets: explicit data license, wrong format for this need

The rendered first-party [Public Data page](https://www.17lands.com/public_datasets) explicitly says:

> Unless otherwise noted, these data sets are licensed under a Creative Commons Attribution 4.0
> International License.

It offers anonymized draft/game/replay gzip exports; the inspected table had entries updated
**2026-10-17**. The [usage guidelines](https://www.17lands.com/usage_guidelines) distinguish these
public datasets from curated site metrics and discourage automated API scraping without explicit
permission. Use the published dumps and their individual exceptions, not that license as permission
to mirror every site statistic. Both pages required ordinary JavaScript rendering; plain HTTP
extraction yielded only an application shell, not a demonstrated protection block.

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permits sharing/adaptation, even
commercially, with attribution, license link and change indication; it gives no warranty for rights
the licensor does not control. This is materially clearer **dataset** licensing than a scraper's
software license. But Arena Limited decks and win-rate contexts do not establish Commander synergy.
Useful future Limited research data; not a substitute for this product's Commander community feed.

### Creator-published Commander lists: small but genuinely explicit grant

The author's [pfirpfel/commander-decks repository](https://github.com/pfirpfel/commander-decks)
describes **“My deck list collection”**, separates the author's paper/online decks, and explicitly
states **“This work is licensed under a Creative Commons Attribution 4.0 International License.”**
The [README](https://raw.githubusercontent.com/pfirpfel/commander-decks/main/README.md) and
[LICENSE](https://raw.githubusercontent.com/pfirpfel/commander-decks/main/LICENSE) were inspected.
This is a clearer provenance/license candidate than a third party's mass scrape: the publisher says
the lists are their own and licenses the work, not merely the scraper. No author permission beyond
that license, independent authorship audit, corpus-size assessment, current legality check or latest
commit date was established here. Card IP and unrelated third-party rights remain separate.

**Tradeoff:** possible attributed examples or a seed for an opt-in collection; one person's lists
are not a statistically meaningful “community popularity” corpus. Preserve attribution, link the
license, mark transformations, and verify individual files/provenance before ingesting them.

### Why not just download a large deck dump?

Search surfaced a Hugging Face
[Moxfield Commander dump](https://huggingface.co/datasets/nsaroiu/moxfield-dump) whose indexed card
claims 122,571 public decklists collected through Moxfield's API. Fetching the raw dataset card
returned **HTTP 401**. No archive was downloaded and no upstream permission was verified.
The claimed count is an uploader claim, **not** an independently verified usable corpus.

Likewise, [a Modern-deck repository](https://github.com/ekohrt/dataset-10000-modern-mtg-decks)
describes scraped Deckstats decks; its search result did not establish a downstream content license
or permission from deck authors/site. These are rejected **as verified reuse candidates**, not
declared unlawful by this research. A Kaggle/Hugging Face badge or an MIT scraper repository alone
cannot supply rights an uploader never obtained.

**Bounded result:** no verified large, current, broadly representative, openly licensed Commander
deck dataset with a demonstrated upstream rights chain was found. Small opt-in author collections
are possible; they have a coverage cost, not a permission shortcut.

## Permission questions worth sending

Do not send anything automatically. A useful request states MTG Helper's actual audience, whether
it is paid, expected traffic, desired fields and whether data reaches an LLM vendor.

Ask each provider to answer these **separately in writing**:

1. **Access/use case:** May we use an official feed for commander/card discovery, not just import a
   user-selected deck? Is this a competing use? What agreement overrides conflicting public terms?
2. **Smallest useful feed:** Could you supply Oracle-ID-based commander/card inclusion counts,
   denominators and sample dates, without usernames, deck prose or complete decklists? Are themed,
   budget and recent-release slices available, with minimum sample-size disclosure?
3. **Rights:** May we store, join, aggregate, display and commercially use those fields? May we
   expose derived scores or export a dataset? Does your grant cover third-party/database rights and
   user contributions, or are author/upstream permissions also needed?
4. **AI boundaries:** Is retrieval-assisted inference allowed? May snippets be sent to our model
   processor under its retention terms? Ask separately about embeddings, evaluation, fine-tuning and
   training; do not bundle them into vague “AI use.” No training is proposed by this note.
5. **Retention/deletion:** What is the raw-cache TTL? May aggregates/history/backups persist? What
   happens when a deck is deleted/private, a contributor opts out, or permission is revoked? Must
   already-derived scores/embeddings be purged or recomputed? Is there a deletion/delta feed?
6. **Operations:** Authentication, approved host, shared quota/concurrency, backoff, daily bulk/delta
   delivery, refresh cadence, schema/version changes, termination notice, costs and support channel?
7. **Credit:** Exact attribution/deep-link requirements, author credit, branding restrictions and
   whether a public recommendations UI must remain free? May we describe you as a data partner?

Provider-specific priorities:

- **Moxfield:** written automated-access and systematic-database permission; competitor approval.
- **Archidekt:** reconcile developer invitations with terms; prefer bounded official bulk/aggregate
  access over expensive repeated search and count requests.
- **EDHREC:** licensed commander-conditioned aggregates, reuse/retention rights and approved delivery.
- **Scryfall:** confirm unusual rank-history/redistribution/paid/AI plans beyond its published rules;
  ordinary documented rank consumption should not be mislabeled as permission to ingest EDHREC.
- **MTGJSON:** which third-party fields have downstream grants, especially rank/saltiness, and their
  notices, commercial-use and retention conditions?
- **Commander Spellbook:** formal data-license scope, combo prose and EDHREC popularity rights,
  deletion/revision semantics and commercial/AI use of exported variants.

## Policy-safe fallback and decision

**Recommendation, not approved architecture:** keep discovery useful without unapproved provider
ingestion. A local Scryfall-backed candidate catalog can use documented card facts and community
Oracle Tags, with optional overall rank as a clearly labeled popularity prior under its usage rules.
It should not pretend to contain commander-specific crowd consensus. Spellbook is a promising
specialized addition through its official API/export, with the data-rights questions above resolved
for the intended use. Neither source proves recommendation accuracy by itself.

For stronger community evidence, choose **an actual permission agreement** or **explicitly licensed
creator/opt-in contributions**, accepting the latter's limited coverage. A user providing their own
export can support private analysis; that alone does not authorize pooling it into a redistributable
global corpus or scraping its original host. Pooling needs its own license/consent basis.

If a provider declines, is silent, challenges access, returns 401/403/429, or changes terms: do not
evade the restriction. Stop unauthorized requests, follow any agreed retention/deletion rules, and
fall back to independently permitted data. Attribution and a low request rate do not cure an absent
reuse grant. A last-known snapshot is a fallback only when its license/agreement permits retention;
“we already downloaded it” is not a universal justification.

Finally, underlying Magic text/art has its own rights layer. The
[Wizards Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy), displaying
**Last Updated: November 15, 2017**, requires free access to covered Fan Content, an unofficial-content
notice and respect for others' IP. Scryfall likewise prohibits paywalling its data. An MIT/CC license
on an aggregator's contributions does not erase these distinct rights. Reassess the actual paid/free
product boundary before monetization rather than assuming paid AI functionality makes everything
permissible or everything prohibited.

**Next decision:** pursue an attributed aggregate partnership (Archidekt/EDHREC first), or accept
lower community specificity with documented local sources. Do not make performance depend on
unapproved real-time community-site requests while that decision is open.

The user's direction during this research is to compare both free and permissioned/paid options,
with no spending or outreach yet. They want a described or explicitly generated commander strategy
linked to source tags and reusable later in deck-agent chat. See the companion
[local-first discussion options](discovery-local-first-options.md) for repository findings and a
proposed experience that keeps card loading independent of AI and provider availability.

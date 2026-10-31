# Discover: Scryfall-only strategy matches

## Replacement workflow

The Discover replacement uses a saved commander strategy and local Scryfall source criteria instead
of an AI-generated card shortlist. This describes the feature-branch implementation, not a production
deployment or approval to spend. The existing experimental capability stays default off. New Cards
and Community Picks retain their own behavior and sources.

1. First-time setup restores current strategy ideas or prepares one set automatically. Full strategy
   cards show the plan before selection; the user can also write their own strategy.
2. **Find cards** prepares source searches, validates and saves the strategy, then loads local matches.
   Separate drafting, term-application and save buttons are not part of the normal flow.
3. The full active strategy stays visible above results. **Advanced search details** is optional:
    selected searches show their grouping and front-face scopes. Oracle tags and printed keywords
    remain editable in bounded searchable pickers; editing them replaces automatic filters with one
    unscoped manual OR search. Merely opening Advanced details preserves all automatic filters.
4. Opening saved Discover results, refreshing them and paging use local Scryfall data without new
   model calls or community-provider requests. Strategy prose is saved independently of the deck
   description and existing deck tag choices, and remains available for future deck-agent integration.

### Source matching, not per-card AI assessment

- Oracle tags and printed keywords are separate source criteria. Unknown terms are rejected, not
  silently invented or turned into global labels. Find cards validates AI-selected terms before saving;
  the user can override them manually in Advanced search details.
- Each saved search has one or two nonempty source groups: criteria are OR alternatives inside a
  group and groups are ANDed. Searches are alternatives, not required roles or quotas. Selected
  parent tags include descendants. Optional card-type scopes use the front face; a Battle is not
  admitted to a creature-scoped search because its transformed back face is a creature.
- Filter before ordering. Use existing global Commander popularity (`edhrec_rank`) from the card
  catalog, unknown/nonpositive ranks last, then stable name and Oracle identity. No match-count
  boost, role round-robin, source-weight cutoff, card-specific exceptions, release-recency boost,
  or Moxfield/Archidekt request. Global popularity is explicitly not commander-specific synergy.
- Results explain only criteria from searches the card actually satisfies. Distinct matched-term
  count remains source evidence, not a relevance score. Source labels do not certify beneficial
  triggers, cast/entry compatibility, simultaneous face access, or strategic usefulness.
- Search paper, Commander-legal nonlands of all release ages within the stored commander/partner
  color union. This does not certify pairing legality, bracket, price, rules synergy or deck balance.
- Physical cards, pending additions and deck-local Discover dismissals are exclusions, not strategic
  evidence. Planning creates pending additions only; completion retains source/legality/copy guards.
- No criteria is an unfinished setup, not a successful empty recommendation result. Cards without
  Oracle tags may still match selected printed keywords. A current valid query can genuinely be empty.

### Availability and AI setup

Scryfall remains the only card-data source. Discover reads a consistent local card/tag publication;
missing or mismatched publications are unavailable rather than empty. A last-good publication older
than two days remains browseable with a source-age/last-known-legality warning. Failed updates do
not erase valid local data. New Cards' separate freshness policy is unchanged.

First-time setup may start one strategy request, and Find cards may start one source-term request.
Persisted work is resumed across reloads instead of regenerated. Explicit retries or **Try other
strategies** may start new work; automatic status polling never does. Ownership, capability, request
size/output bounds, timeout, concurrency and single-use request guards remain enforced. Current setup
is not blocked by dollar estimates or historical unknown-price holds. Unknown costs remain unknown
in the preserved receipt/accounting history, never silently priced as zero.
Model errors must not erase saved strategy or make local browsing depend on AI availability. The AI
term-selection catalog retains strategy retrieval and adds commander/partner source tags, their
immediate source hierarchy neighbors, and commander-text retrieval. At most 160 Oracle tags and
120 printed keywords are supplied, with source descriptions capped at 600 characters and an explicit
truncation marker. Complete commander facts are included; private deck contents are not. The draft
may select at most eight distinct tags and eight keywords across at most six searches. It must not
fill roles mechanically or confuse a cast trigger with direct reanimation. These prompt safeguards
are not a per-card semantic validator. Suggestions are not exhaustive. The full source catalog remains
searchable manually, but only 20 suggestions per picker are rendered at a time. Browsing does not
need the historical rules snapshot.

Current setup uses `app-strategy-terms-v3`, one request bounded at 80,000 input bytes/token-reservation
units and 4,000 output tokens; the conservative reservation is $0.0248, not an invoice. The provider
schema enumerates the exact frozen catalog in global `oracle_tag_ids` and `printed_keywords` arrays,
each capped at eight entries. Search groups use zero-based indices into these selected arrays,
not the input catalog. The backend rejects duplicate choices, missing/repeated indices, empty groups
and equivalent searches, then decodes into the existing grouped queries. No trimming or repair calls.
An unavailable source kind permits only []; neither kind available stops before a provider attempt.
These structural limits do not establish strategic usefulness or guarantee every response is valid.

Retain this single-call baseline. Result-aware refinement remains an offline research experiment,
not an application setup stage: the fresh Yuna/Meren comparison passed the v3 contract on all four
calls, but refinement reduced the lead's top-twenty usefulness scores and reachable-reference
coverage on both decks. Do not automatically narrow searches from result counts or regenerate saved
criteria. See [the comparison report](research/discover-bounded-result-aware/report.md).

The old v1/v2 prompts and parsers remain historical research/accounting only. New setup does not
resume or reuse their runs. V2's already decoded grouped results remain owner-readable through the
term-run view, and historical traces/receipts/unknown holds remain unchanged. Existing saved strategies
are not regenerated. No live-call reliability or recommendation-quality improvement is claimed from
offline schema/decoder checks.

Saved strategies store `queries` once rather than redundant flat term arrays. Schema upgrade converts
existing flat criteria into one equivalent unscoped OR search, preserving prose, owner, revision and
selected identities. It does not regenerate existing criteria. A user explicitly choosing Find cards
can prepare new criteria. Ship the matching backend/frontend contracts together. Cursor state binds
ordering version and ranking metadata as well as strategy, source, commanders and exclusions.

The old card-generation action is retired. Historical runs, traces, attempts, source snapshots, costs,
unknown holds and pending-plan origins remain history/accounting data; they are not current strategy
matches and are not replayed through the replacement workflow.

See [the glossary](../GLOSSARY.md) for the distinction between Strategie-Treffer and New Cards'
Tag-Treffer, and [the research discussion](research/discovery-local-first-options.md) for context.

## Historical pilot checkpoint (superseded)

The remainder records the prior three-stage card-generation pilot and its historical operating
limits. It is retained to explain preserved runs, immutable profiles and accounting records, not as
the current Discover interaction contract. New card-generation work described below is retired.

Discover is implemented but **default off**. This document is not live enablement, spending approval,
or deployment verification. New Cards retains its existing workflow;
Top Picks is labeled Community Picks with the same backend, source selection and caches.

This document describes the actual first pilot and its limitations, not a recommendation-accuracy
claim. Account enablement and the proposed spending ceilings require separate confirmation.
**Draft 3 commander strategies** offers selectable source-only directions before card generation.
Each has pace, early setup/ramp, main engine, possible payoff, explanation and uncertainties; a
complete win condition is not required. Choosing one copies all phases and uncertainties into the
editable discovery goal, without automatic saving or card generation. Suggestions and free source
matches use the shared artwork-first card grid.

## Behavior

- Commander-only, eligible paper Commander nonlands. Partner/background decks and collection scopes
  are gated. Physical/planned cards are exclusions, never model support.
- Explicit goals and literal Oracle/type/keyword/mana-value constraints. Narrative preferences are
  unverified; no bracket, price, collection-ownership or combo guarantee is implemented.
- Source browsing, inspection, rules lookup, refresh and pending additions need no model calls.
- Explicit **Draft 3 commander strategies** makes one separately bounded call using only complete
  commander facts. Compare the unverified directions, select one **Use as goal**, edit its complete
  phase/uncertainty goal if needed, then explicitly Generate cards. Pace is a preference, not a speed
  guarantee. Blank or existing edited goals survive refresh; drafting never writes the saved deck
  description or discards previous card recommendations.
- Only explicit **Generate** starts the card run: plan, one complete replacement revision, then
  assessment of at most 32 independently admitted cards. No eligible shortlist means no review call.
- Invalid global identities/JSON fail the review. Independently valid assessment rows survive bad
  neighbors; failed/missing/unassessed rows are not recommendations. Literal quotes are not rules
  certification. Broad searches and small samples are not exhaustive catalog coverage.
- Plan & Searches includes native rules lookup and owner-only JSON diagnostics/export. The trace
  carries actual initial/replacement searches, counts, samples, errors, raw answers and usage.
- Planning creates one pending addition idempotently, never changes physical cards. A planned cut
  conflicts rather than silently being canceled. Current source legality/color/copy limits are
  checked at planning and transactional completion, including revision completion paths.
- Origin flags survive quantity changes, normal plan merges and Oracle duplicate repair. Manual
  Cards/Rule 0 paths are not relabeled as Discover and do not acquire the flag automatically.
- Pilot feedback is run-scoped and isolated from retired personalization data and evaluation fixtures.

## Shared code and preserved research

Pure catalog/search/admission/evidence/rules operations and historical prompt profiles live under
`backend/src/mtg_helper/services/recommendations/`. Application modules never import `scripts.*`.
Evaluation CLIs retain their file/provider adapters, frozen pools, protocols and exclusive ledgers.
The separate `app-pilot-v1` contract uses real independent discoveries, not diagnostic fixtures.
`app-strategy-v2` is a one-call, three-choice draft, not a discovery/assessment pool or card advice.
It reuses the same run/attempt ledger, account lock and unknown holds; no schema migration or new
spending account is needed. A draft cannot authorize recommendation-origin additions. Archived
`app-strategy-v1` records remain strategy history, never replace card results and retain their
original private trace/accounting. They are stale/nonselectable, not adapted into invented choices
or resumed with new bounds. Unknown holds from any profile still block spending.

Offline suite, including the preserved research checks:

```bash
cd backend
uv run --no-sync pytest -q -W error -m no_db
```

`.github/workflows/recommendation-core.yml` runs these offline checks without secrets, a database,
network calls or ignored research caches. Full catalog replays are separate provisioned checks.
Existing spent/stopped authorizations are never reusable, including the unknown Sol timeout.

## Sources and migrations

`db.apply_schema` adds the pilot tables and fields idempotently. It does not enable the capability.
Normal Admin card sync publishes complete normalized root/face facts alongside unchanged legacy
New Cards facts, in the same catalog transaction. Immutable compressed card/rules snapshots are
hash checked, bounded and retained in PostgreSQL. Read-only indexes cache two snapshot pairs.

Artwork is optional current-catalog printing metadata, batched by Oracle identity after authorizing
source/status/run reads. Only HTTPS URLs on `cards.scryfall.io` are exposed; missing/unsafe images
fall back to readable name tiles. Images never enter provider payloads, gameplay snapshots, cursor
hashes, evidence or spending fingerprints. Source facts/AI advice remain pinned even if artwork
changes. The UI labels this distinction; artwork is not a guarantee of an owned/exact printing.

The complete official rules text is packaged under
`backend/src/mtg_helper/services/recommendations/data/rules-20260925.txt`, not an ignored cache.
Its original SHA-256 is
`8d860e451f20f38865b725b42d82feb714c725373dd8f3b32b8652b3eeb070ca`.
Git attributes preserve the original rules, frozen JSON evidence and input-fixture bytes across
Windows and Linux; staged blobs were verified byte for byte before committing.
Malformed/missing optional rules prevent experimental readiness, not legacy startup/card sync.
Rules updates currently require a reviewed package/hash change and normal publication; there is no
runtime user-supplied rules URL. Card sync does not ask a model to classify capabilities.

`source_repository.prune(pool)` is explicit maintenance, not polling/startup work. It conservatively
retains every run-referenced generation, latest cards and rules, and recent unreferenced snapshots.
Historical referenced snapshots therefore do not expire in this first pilot. Missing explicitly
requested snapshots return unavailable rather than replaying against current sources.

Deleting a deck leaves its run/attempt spend records and unknown holds intact. Deleting an account
uses existing account cascade semantics; limits are account scoped, not a global identity quota.

## Provider and durable spending

The following are implemented **estimate guards**, not approved live spending or provider caps:

| Bound | First pilot |
|---|---|
| Model/profile | `gpt-5.6-luna` / `app-pilot-v1`, standard tier |
| Requests | At most 3; no application or SDK retry |
| Timeout | 300 seconds per request |
| Run reservation | 67,750 integer microdollars ($0.06775) |
| Run ceiling | 100,000 microdollars ($0.10) |
| Account/day ceiling | 1,000,000 microdollars ($1), UTC |
| Phase input bytes/output tokens | 20,000/5,000; 60,000/5,000; 95,000/10,000 |

The optional `app-strategy-v2` draft has one `plan` attempt, a 20,000-byte framed input bound and
4,000-output-token bound. It reserves 9,800 microdollars ($0.0098), under its 10,000-microdollar
($0.01) estimate ceiling. It shares the same $1/account/UTC-day allowance, one-active-run lock and
unknown holds as card runs. Using/editing a completed draft costs nothing; a later explicit card
Generate retains its independent three-call bounds above. Neither action starts the other.

Input reservations use $0.25/M tokens conservatively, output $1.20/M, with no assumed caching.
Rates must be rechecked before enabling. Unknown usage/model/tier or provider errors retain an
unknown hold and stop dependent stages. These holds survive UTC rollover and block new spending.
Never erase an attempted row or create a replacement authorization to bypass a hold.

Account row locks serialize reservation/settlement. A unique request key binds immutable inputs;
reusing it with different inputs is rejected. One active run/account is enforced in PostgreSQL.
Different request keys conflict while a run is active. Attempts are claimed exactly once and
committed before HTTP, with fenced 10-minute leases. Expired/restarted work is interrupted, never
resent. Late known receipts settle once, even when their worker cannot publish results anymore.
Response/request IDs are retained when available. In-memory tasks are executors, not durable state.

Unknown-billing reconciliation is intentionally not a self-service UI operation. A verified late
receipt can settle through the run repository. Otherwise an operator must establish provider billing
and obtain an explicitly reviewed reconciliation; there is no safe “clear hold and retry” button.

## API and feature gate

The Admin page has a **Discover · Experimental** access panel near the top. It loads the signed-in
account and effective capability, then offers **Enable for my account** or **Disable for my account**.
These explicit actions use the existing authenticated admin feature-flag endpoint with that account's
ID; the panel never changes the global default or other accounts. Loading/refreshing status is
read-only, and toggling access never generates recommendations. After enabling, reload an open deck
to see the Discover tab. An uncertain save requires **Refresh status** before another change.
This convenience control does not approve spending or establish source readiness/provider prices.
Disabling stops future run stages; a request already in flight may still bill.

All deck recommendation endpoints require authenticated deck ownership and the `recommendations`
capability, default false, under `/api/v1/decks/{deck_id}/recommendations`:

- `GET /status`, `POST /preview-query` (literal cards and native rules, no provider request).
- `POST /runs` (explicit card-run request key/input; 202) and `GET /runs/{run_id}`.
- `POST /strategy-drafts` (explicit request key only; 202). Status returns the latest draft in
  `strategy_run` independently of the latest card `run`, including archived strategy versions.
  A current completed draft's `strategies` contains exactly three choices: `title`, `pace`,
  `early_game`, `engine`, `payoff`, `explanation`, `uncertainties` and a deterministic `goal` of at
  most 1000 characters containing every phase/uncertainty without truncation. Card runs have no
  choices. Lost-response retries retain the same key; keys cannot be reused across paid profiles.
- `GET /runs/{run_id}/trace` (private diagnostics).
- `POST /runs/{run_id}/candidates/{oracle_id}/plan` (validated recommendation).
- `POST /candidates/{oracle_id}/plan` (explicit manual, unassessed source addition).
- `POST /runs/{run_id}/feedback` (isolated feedback).

Card cursors bind commander, query and source pair; rules continuations require the pinned rules
hash and exact terms. Polling projects persisted results and overlays current exclusions, rather
than reconstructing sources or evaluating advice. Missing sources do not disable Cards or Community
Picks. Revoking the capability stops future run stages; an in-flight request may still bill.

## Recorded verification and remaining gates

See `backend/tests/test_recommendation_{core,pilot}.py` and the frontend Discover tests.
Database/API/SDK tests use isolated PostgreSQL and replace external HTTP only. They do not
exercise paid model behavior.

Historical implementation checks (not rerun merely by editing this document):

- 164 offline backend checks: all 135 preserved evaluation checks, 10 application-core checks,
  6 strategy-choice checks and 13 artwork checks.
- 44 real isolated PostgreSQL checks: 15 Discover, 8 strategy-choice, 1 artwork, 17 legacy New Cards
  and 3 card-identity checks.
  Covers source-generation changes, single-use claims, unknown holds/UTC rollover, deleted-deck
  spending, late receipts, ownership, isolated feedback, current completion legality and origins
  through manual merge, Oracle repair, partial and batch completion.
- All 98 frontend tests (including 18 admin-access, 18 strategy and 2 image checks), frontend
  typecheck/lint/format, full backend Ruff lint/format and `ty check src/` passed.
  Draft checks cover separate reservations/profile fencing, duplicate workers, expiry/late settlement,
  shared daily allowance, cross-profile/UTC unknown holds, explicit goal use and no automatic deck edit.
- Five offline historical replays preserved all 37 archived research JSON files byte for byte.
- Wheel packaging verified the complete official rules text/hash. Clean schemas were initialized
  by database tests; reapplying the schema preserved all 22 immutable test source snapshots.
- Independent boundary review found one P2: card pagination dropped its pinned rules hash. The
  repaired response/controller and fingerprint behavior passed a focused independent recheck and
  a real rules-publication regression.
- Earlier independent read-only review of the single-draft `app-strategy-v1` paid/action boundary
  found no supported blockers. It inspected profile-specific bounds/fencing, shared holds/settlement, request-key
  identity, status separation and explicit goal use; it did not independently rerun the suites or
  establish paid-model behavior/semantic correctness.
- The image/three-choice independent boundary review found a P2: trace refresh still recognized only
  v1 and would switch v2 strategy traces to card traces (or disable refresh without card results).
  The family-aware heading/refresh repair failed the two v2 regressions before the fix, then passed
  all four current/archived-with/without-card cases. A focused independent recheck reran all 11
  strategy controller tests and found no remaining supported blocker. No browser/paid-model proof.
- Mutation checks detected unsafe artwork passthrough and missing selected-phase goal context;
  the unchanged-on-disk implementation then passed all 19 targeted backend tests.

The broader existing planned-change suite is **not a pass**:
`test_planned_addition_is_excluded_from_physical_deck` expects two planned Sol Rings, but singleton
clamping yields one (planned deck count 2, not 3). This exact failure was reproduced on pristine
`HEAD` (`8c1db1aa`), outside this implementation. No unrelated legacy behavior was changed to make
that assertion pass. No browser E2E or paid application-model test was performed.

Before any live pilot: confirm account-specific enablement, spending bounds, provider rates and
full-source readiness on the target deployment. New Cards migration, broader deck-aware analysis,
model comparisons and release sweeps remain separately scoped and authorized. This implementation
has not established semantic accuracy or measured real application model latency.

# Replace global card labels with Scryfall

## Now

**Canonical source publication implemented and tested; replacement is still in progress.**
Scryfall becomes the only global card-label and printed-keyword source. The user explicitly keeps
personal deck-local manual categories. [Measured coverage and limits](research/scryfall-tag-coverage/README.md)
support the source choice, not an accuracy claim or adoption of the experimental fixed search lanes.

The first implementation slice adds bounded, validated Oracle-tag ingestion to the existing Scryfall
sync. It publishes facts, history and tags in the same transaction; keeps direct memberships separate
from descendant searches; and retains source metadata, weights, annotations, receipts and hashes.
Admin status/UI now expose exact publication and upstream update times and a mismatched-generation
warning. **Existing label consumers, legacy sources, prompts and global label columns still remain.**
They have not been cut over or removed. No paid calls were performed. The publication schema and
sync have now been deployed to the approved homeserver production database after actual-data rehearsal.

Acceptance evidence for this slice:

- Backend: 188 scoped tests passed, full Ruff lint/format and `ty check src/` passed. Tests cover malformed
  archives/receipts, resource bounds, unknown IDs, hierarchy cycles, publication rollback, partial
  generations, superseded writers, MVCC readers, snapshot verification and personal-data preservation.
- Populated schema upgrade reapplied twice preserves accounts, descriptions, saved old theme intent,
  categories, quantities, plans, inventory, preferences, feedback and historical snapshots exactly.
- Frontend: 9 scoped tests, project lint/typecheck and changed-file formatting passed. The UI explicitly
  says that source publication is not yet label-consumer cutover.
- A deliberate non-transitive membership mutation failed the parent-search test; restored code passes.
- Live Scryfall sync in **`mtg_helper_scryfall_sync_check` only**: 32,165 Commander-relevant cards,
  4,577 tags and 236,707 direct memberships, in 24.46 seconds. Card/tag binding and persisted row counts
  were verified. A final live repeat after resource-bound fixes took 25.17 seconds and reproduced
  identical card/tag snapshots. Normalized card hash:
  `6aae3dd11d54589517423aeb56e0399f458d9d2deb8f765da517a887475fac34`; tag snapshot hash:
  `a6d8a5540e824e91836b27a29eeebe5864dabaeb8c7ba173a189fbdc7d89129a`.
- The original local application database still has 31,692 cards and no `scryfall_tag_state` or `new_card_catalog`
  relation. It was inspected, not upgraded or synced. The disposable verification database is retained.

Independent review identified two resource blockers: implicit HTTP decompression before the transfer
limit, and the inherited printing-history parser's missing decompression bounds. Both were repaired:
all three bulk files and the manifest now use raw, identity-encoded HTTP transfers with byte limits;
history additionally has decompressed-total, line and record limits. Streaming regressions reject HTTP
compression before reading the body, stop oversized transfers early, and reject history line bombs
before JSON parsing. The focused independent recheck confirmed both blockers resolved, ran 39
no-database tests, and found no repair-induced regression. Database/live-sync and frontend evidence
was executed by the implementation owner, not independently rerun. This approval covers the
publication foundation only, not unfinished label-consumer migration or application deployment.

Local-only [isolated staging](scryfall-label-staging.md) is now running at `http://localhost:3000`.
A staging Admin sync completed successfully and reports matching generations: 32,165 cards,
4,577 tags and 236,717 current direct memberships. Staging has its own database volume and runtime
secrets, no working AI key, and no application-data mounts. The original application database remains
stopped and untouched. Authentication redirects/provider routing passed; interactive Google login
and authenticated browser verification remain for the user. This is not production deployment or
label-consumer cutover.

**Homeserver production publication is deployed and verified**; see the
[production release record](scryfall-publication-production.md). Both rehearsal and actual rollout
preserved all 25 personal tables and historical source snapshots through schema/startup/live sync.
The final maintenance backup is retained, and production reports matching generations: 4,577 tags,
236,717 direct memberships. Backend/frontend are running; the original sync worker has resumed.
The inherited startup schema separately backfills legacy `mtgjson_tags` rows, not personal state.
No paid model calls were made, and unrelated research experiments are excluded from release PR #18.
Public ingress requires the user's normal browser access; the unauthenticated automation probe was
403. This deployment is publication only, not the unfinished global-label consumer cutover.

Next: canonical UUID/printed-keyword API, filters, source
snapshots and planner queries; then remove the old labeling paths together. Do not treat ingestion
alone as completion of the sole-source migration.

## Contract

- Oracle tags join by Oracle identity, not printing; retain source UUIDs, labels, descriptions,
  aliases, hierarchy, weights and annotations with their source generation. Art tags are excluded.
- Printed keywords come directly from Scryfall card facts. No MTGJSON keyword catalog, local regex
  tagging, curated mechanic descriptions or community-derived card membership fallback remains.
- Derived local `traits` and `token_types` are classifications too: retire their classifier/consumers
  or replace their searches with source tags or literal source predicates. Do not relabel them as
  Scryfall facts. Card names, types, faces, colors and costs remain ordinary source facts.
- The global tag inventory comes from Scryfall. Models may select valid source tag IDs for a goal;
  they cannot assign permanent new labels to cards. Query intent and contextual fit remain prose.
- Parent searches include descendant memberships, without rewriting direct source taggings.
  Missing labels never establish an ineligible card or lack of fit. Keep literal/name discovery.
- User descriptions, deck-local categories, plans and inventory remain user data, not global labels.
  Saved old theme/mechanic choices are user intent: preserve their meaning for review rather than
  silently deleting them or making a fuzzy tag match authoritative.

## Implementation slices and acceptance evidence

1. **One canonical source publication.** Extend the existing Scryfall bulk/admin sync with Oracle
   tags. Parse current gzip JSONL; bind card/tag generations; validate IDs and hierarchy; publish
   atomically and retain last-good Scryfall data on failure. Report failed publication and freshness
   explicitly; never replace a complete catalog with a failed/partial one. Reuse current scheduling.
   Verify malformed input/network/partial-sync tests, a local sync and preserved last-good reads.
2. **Replace label consumers together.** Update source card responses, tag/keyword catalogs,
   browsing, builder role queries, commander suggestion/planning prompts and recommendation filters
   to canonical Scryfall tags/keywords. Source role/tag relationships must not come from hand-written
   card classifiers or a new curated tag-to-role ontology. Unknown relationships remain explicit.
   Verify backend/API/frontend contracts, tag UUID resolution and descendant filtering through the
   application routes, not only pure helpers. Snapshot source labels where runs depend on them.
3. **Remove the old paths.** Delete rule taggers and unused classification scripts; remove MTGJSON
   label sync/catalogs, Moxfield/Archidekt label membership, curated theme-label generation, associated
   admin controls, old global label columns/indexes and runtime fallbacks. Retain unrelated community
   recommendation statistics only if they do not supply labels; do not turn this into another engine
   rewrite. Inspect genuinely unused MTGJSON metadata code before retaining it.
   Verify structure-aware import/schema checks plus repository searches for retired writers/readers.
4. **Reviewed data migration and preservation.** Back up the local database before destructive DDL;
   specify treatment of saved old theme selections before removal. Preserve deck categories, saved
   descriptions, quantities, plans and feedback. Apply schema in the test database first, then only
   the explicitly approved local application database. Remove old paths rather than add a dual format.
   Verify before/after user-data counts/content and upgrade tests on representative populated data.
5. **Recommendation proof.** Let the existing bounded planner choose source tag queries from actual
   commander/goal context. Keep original facts authoritative, label context out of fit review
   initially, and enforce unchanged admission/assessment limits. Test invalid IDs, missing labels,
   stale generations, provenance, eligibility and budget displacement. Before accuracy/cutover claims,
   compare automatic planning on unused strategies with blinded usefulness/rules review. Paid calls
   require fresh authorization; no old ledger can be resumed or reset.

## Error policy and exclusions

The publication snapshot binds normalized card facts to the Oracle-tag archive hash and both export
receipts. `scryfall_tags` stores upstream metadata, `scryfall_tag_memberships` stores direct source
memberships, and `scryfall_tag_descendants` stores only validated transitive hierarchy expansions.
`scryfall_tag_state` identifies the matching durable card/tag snapshots in `recommendation_sources`.
No new classifier or curated tag-to-role mapping is introduced. DELETE/COPY publication is MVCC-safe;
it never truncates live source tables. Current source data uses 11,910 hierarchy relations and 434,922
expanded memberships; independent byte/record/expansion limits bound untrusted source processing.

Malformed/partial tag publication fails visibly while retaining the previous Scryfall generation.
Unresolved query IDs produce an explicit query error, not an empty-success result or inferred label.
A failed enrichment never erases cards or deck-local choices. No new dependency, classifier, graph
framework, paid catalog-wide labeling, automatic physical edits or per-click model call is needed.

The existing Scryfall sync still invokes Oracle-identity repair after publication. That separate repair
can clamp illegal singleton quantities or merge duplicate printings. The label-data migration must not
use that behavior as a preservation operation: compare saved state before/after DDL and review any
identity repair separately. The sync preservation regression uses a valid multi-copy basic land;
the schema-upgrade regression preserves all stored quantities and intent without repair.

Independent review is required before merging schema/API and global label replacements. The recorded
production approval covers the publication foundation only; it does not authorize destructive
consumer-cutover DDL, data deletion, paid evaluation or claims of better recommendation accuracy.

# Data model

The authoritative schema is
[`backend/src/mtg_helper/sql/schema.sql`](../../backend/src/mtg_helper/sql/schema.sql).
It includes upgrade statements as well as initial table definitions; inspect both when
changing a column. This guide groups responsibilities rather than duplicating every field.

## Active data

| Tables | Purpose |
|---|---|
| `cards` | Scryfall printing and Oracle identity, rules, prices, canonical selection, and legacy retrieval fields |
| `accounts` | Google subject, email, display name, account identity |
| `decks`, `deck_cards` | Commander/partner, strategy, bracket 1–5, stage/targets, physical quantities and category arrays |
| `collections`, `collection_cards` | Account-owned inventory by printing and foil status |
| `deck_card_plans` | Pending additions/cuts, separate from the physical deck, with experimental origin flags |
| `deck_revisions`, `deck_revision_changes` | Atomic applications of selected plans and their recorded changes |
| `deck_snapshots`, `deck_snapshot_cards` | Point-in-time deck copies for history/comparison |
| `feature_flags` | Global and per-account capability overrides |
| `new_card_catalog`, `new_card_catalog_state` | Complete source facts, release metadata, publication state |
| `new_card_assessments`, `new_card_assessment_history`, `new_card_dismissals`, `new_card_jobs` | Deck-specific advice/cache history, dismissals, account leases and quotas |
| `recommendation_sources` | Immutable, compressed, hash-bound card/rules/tag snapshots |
| `recommendation_accounts`, `recommendation_runs`, `recommendation_attempts`, `recommendation_feedback` | Discover spending holds, inputs, results, attempts, isolated run feedback |
| `scryfall_tags`, `scryfall_tag_memberships`, `scryfall_tag_descendants`, `scryfall_tag_state` | Canonical tags, direct memberships, hierarchy closure, matching publication |
| `mtgjson_card_metadata`, `mtgjson_keywords` | Still-active legacy metadata/keyword sources |
| `moxfield_hubs`, `moxfield_hub_card_stats`, `archidekt_tags`, `archidekt_tag_card_stats` | Legacy community catalogs and membership evidence |
| `theme_groups`, `theme_group_members`, `theme_group_suggestions` | Shared/admin-curated theme grouping |
| `moxfield_commander_recs`, `archidekt_commander_recs` | Cached commander-level community picks |

Deck ownership uses `decks.owner_email`, not an `owner_id` foreign key. Inventory and
experimental jobs/results use account IDs. Cards have both local IDs and Scryfall printing
IDs; Oracle identity groups equivalent gameplay cards across printings. Preserve that
distinction when merging cards, plans, or inventory.

`deck_detail_view` joins physical deck entries to card metadata. Physical quantities and
`categories TEXT[]` are distinct from the planned-change overlay. Applying plans records
a revision; a pending addition is not already present support for physical-deck advice.

## Retained, retired personalization data

`preferences`, `deck_feedback`, `deck_coach_memory`, and `account_ranking_weights` remain
in the schema to preserve old data. Current recommendation/assistant paths do not use
them as personalization inputs, and their old editing/feedback APIs are removed.
Discover's `recommendation_feedback` is separate run-scoped data, not a replacement
cross-deck learning system.

`conversation_turns` is removed by the schema. Current Coach turns receive bounded
client history; Assay correlation does not provide persisted conversational memory.

## Schema safety

Read [VERIFY.md](../../VERIFY.md) before applying schema changes. Isolated tests recreate
only a disposable local `_test` database. Live-data development disables startup maintenance;
normal application writes still affect shared data. Rehearse migrations locally and follow
the [production preservation procedure](../../docs/scryfall-publication-production.md)
before a production schema deployment.

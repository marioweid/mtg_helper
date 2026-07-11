# Multi-Source Theme Groups Design

## Goal

Extend the existing Moxfield hub pipeline with Archidekt deck tags while preserving the working
Moxfield implementation. Present equivalent tags from both sources as stable, editable theme
groups. Let administrators disable noisy source tags and curate mappings without code changes.

## Scope

This release will:

- retain the existing Moxfield catalog and card-statistics pipeline;
- add an independent Archidekt tag catalog and card-statistics pipeline;
- calculate tag relevance against a source-local untagged deck baseline;
- introduce shared theme groups above both source catalogs;
- let administrators manage groups, memberships, and source-tag availability;
- expose enabled groups and enabled ungrouped tags to theme selection, prompts, and retrieval;
- preserve legacy Moxfield selections during migration.

This release will not add fuzzy automatic grouping, cross-source score calibration, bulk admin
editing, hard deletion, or theme-to-card-role inference.

## Architecture

Moxfield and Archidekt remain separate ingestion adapters with separate persistence. A small
source-neutral grouping and resolution layer sits above them:

```text
Moxfield catalog -> Moxfield statistics ----\
                                            -> shared theme resolver -> picker, prompts, retrieval
Archidekt catalog -> Archidekt statistics --/
                              ^
                              |
                   editable theme groups
```

This additive approach limits regression risk. The existing Moxfield fetching, sampling,
scoring, and storage behavior remains intact until the shared resolver has been verified.

## Data Model

### Existing Moxfield tables

Keep `moxfield_hubs` and `moxfield_hub_card_stats`. Add an administrator-controlled `enabled`
boolean to `moxfield_hubs`, defaulting to true. Keep `active` with its current upstream-liveness
meaning:

- `active`: the hub still exists in the latest upstream catalog;
- `enabled`: MTG Helper chooses to sync and use the hub.

Catalog refreshes may update `active` but must never reset an administrator's `enabled` choice.

### Archidekt tables

Add `archidekt_tags` with:

- a local primary key and stable upstream identifier or slug;
- source slug, normalized local tag, name, and optional description;
- `active` and administrator-controlled `enabled` flags;
- first-seen, last-seen, catalog-sync, last-card-sync, last-error, and last-error-at fields.

Add `archidekt_tag_card_stats` with the same statistical shape as
`moxfield_hub_card_stats`: tag and card references, tagged/baseline deck counts and percentages,
synergy score, sample sizes, and fetch timestamp.

### Shared groups

Add `theme_groups` with:

- stable unique slug;
- editable label and optional description;
- display order;
- enabled flag;
- soft-deletion timestamp;
- created and updated timestamps.

Add `theme_group_members` with:

- group reference;
- source discriminator: `moxfield` or `archidekt`;
- nullable `moxfield_hub_id` and `archidekt_tag_id` foreign keys;
- created and updated timestamps.

A check constraint requires exactly one source foreign key and requires it to match the source
discriminator. Partial unique indexes on each source foreign key ensure that one source tag
belongs to at most one shared group. A tag may also belong to no group.

## Catalog and Statistics Pipeline

The full refresh order is:

1. Apply the schema.
2. Run the existing Scryfall and MTGJSON syncs.
3. Refresh the Moxfield catalog and enabled stale-hub statistics.
4. Refresh the Archidekt catalog and enabled stale-tag statistics.
5. Rebuild theme selection data through the shared resolver.
6. Run the existing rule-based card tagging pass.

For each Archidekt tag, sample tagged decks and compare card frequency with an untagged
Archidekt baseline. Use the same initial minimum deck count, tagged-deck frequency, and synergy
thresholds as Moxfield. Keep those constants source-local so they can be tuned independently
later without changing the shared resolver.

Archidekt and Moxfield statistics are not averaged. When a group contains matches from both
sources, a card's group relevance is the maximum enabled member score. This follows the current
Moxfield multi-hub behavior and avoids double-counting overlapping deck populations.

Disabled or inactive tags are excluded from new statistics work, prompts, selection, and
retrieval. Disabling is reversible and does not delete catalog records, mappings, or historical
statistics.

## Grouping Policy

Seed only high-confidence equivalent mappings, including common themes such as +1/+1 counters,
artifacts, aristocrats, blink, enchantments, equipment, lifegain, reanimator, spellslinger,
tokens, Voltron, and creature types for which both catalogs clearly agree.

Do not perform fuzzy grouping during routine sync. Newly discovered tags appear under
`Ungrouped`, where an administrator can assign them. This makes incorrect associations visible
and correctable instead of silently affecting recommendations.

An enabled ungrouped source tag remains selectable. Its selection identity must include the
source so equal or similar slugs from different providers cannot collide.

## Admin Experience

Add a theme-management area to the existing admin panel. It supports:

- listing, searching, and filtering shared groups and source tags;
- filtering tags by source, grouped state, upstream activity, and enabled state;
- creating, renaming, reordering, enabling, disabling, restoring, and deleting groups;
- assigning an ungrouped source tag to a group;
- moving a source tag directly from one group to another;
- unassigning a source tag back to `Ungrouped`;
- enabling and disabling individual Moxfield hubs and Archidekt tags;
- viewing source identity, last sync, last error, sample sizes, and matched-card count;
- running a full source sync or manually refreshing one source tag.

Deleting a group requires confirmation and is implemented as soft deletion. Its source members
return to `Ungrouped`. The historical group record remains restorable, especially when saved
decks still reference its stable slug. Restoring a group does not automatically reclaim members
that an administrator assigned elsewhere after deletion.

All mutations must report duplicate slugs and membership conflicts clearly. Group and source-tag
changes take effect in selection and retrieval without a deployment.

## Public Selection and Compatibility

The public theme catalog returns:

- enabled, non-deleted groups in administrator-defined order;
- enabled members summarized beneath each group where useful;
- enabled, active, ungrouped source tags in an `Ungrouped` section.

The frontend selects a stable group identity or a source-qualified ungrouped identity. A group
selection expands to its enabled, active members before scoring. A direct ungrouped selection
resolves to its one source tag.

Keep `/tags/hubs` temporarily as a compatibility route that returns the new catalog shape
accepted by the existing picker. Rename frontend concepts from hub-specific to theme-specific as
a contained follow-up inside the same implementation, without requiring an immediate public
route removal.

During migration, the resolver accepts both shared group slugs and legacy Moxfield hub tags.
Existing `decks.archetype_tags` values are migrated to group slugs when an unambiguous seeded
mapping exists. Unmapped Moxfield values remain valid as source-specific ungrouped selections.
No saved deck should lose its selected theme because of the migration.

## Failure Handling

- A failure in one source must not erase or invalidate the other source's data.
- Catalog upserts are transactional per source.
- Statistics replacement is transactional per source tag.
- A failed tag refresh retains its last successful statistics and records its error and time.
- An upstream tag disappearance sets `active` false without deleting its mappings or history.
- Empty or malformed upstream responses must not mark an entire existing catalog inactive.
- Group mutations reject duplicate slugs and multiple-group membership.
- Retrieval ignores unresolved, disabled, inactive, or soft-deleted selections safely.

## Testing

### Backend unit tests

- Archidekt catalog parsing and normalization;
- extraction of deck identifiers and card names;
- baseline scoring thresholds and exclusions;
- maximum-score resolution across group members;
- source-qualified ungrouped selection parsing.

### Database and service tests

- one-group-per-source-tag uniqueness;
- administrator `enabled` state survives catalog refresh;
- disabled tags do not sync or score;
- delete, unassign, and restore behavior;
- legacy Moxfield selection compatibility and migration;
- one-source failure leaves the other source unchanged;
- failed refresh retains previous statistics.

### API and frontend tests

- group create, edit, reorder, delete, and restore;
- assign, move, and unassign membership, including conflicts;
- source-tag enable and disable;
- grouped and ungrouped catalog rendering;
- admin search and filters;
- manual one-tag and full-source sync controls.

## Deferred Container Idea

Archidekt includes a mixture of strategies, mechanics, creature types, formats, metadata, and
role-like tags such as Draw and Ramp. A later release may add editable UI-only containers above
shared groups. It must not infer per-card deck roles from theme membership: a card overrepresented
in Draw-tagged decks is not necessarily a draw spell. MTG Helper's existing rules-text-based card
role classification remains the source of truth for draw, ramp, and interaction slots.

## Success Criteria

- Moxfield behavior and existing saved theme selections continue to work.
- Archidekt tags and card statistics refresh independently.
- Equivalent Moxfield and Archidekt tags appear as one selectable group.
- Cards matched by either source are ranked using the strongest source score.
- Administrators can correct mappings and disable noise without code or deployment changes.
- Newly discovered tags are visible in `Ungrouped`.
- A source outage or malformed response does not destroy previously valid theme data.

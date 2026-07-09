# Keyword Retrieval And Theme Subcategories Design

## Goal

Remove semantic card matching because its accuracy is worse than the structured
signals already available. Card suggestions should be driven by EDHREC tags,
MTGJSON/card keywords, text search, commander/theme EDHREC data, and Moxfield
deck inclusion. The theme stage should let the user inspect top cards for each
selected commander keyword instead of mixing all selected keywords into one
undifferentiated list.

## Scope

In scope:

- Remove Qdrant semantic search from suggestion retrieval and ranking.
- Remove embedding generation from the card sync/admin pipeline.
- Remove Qdrant payload sync from tag generation.
- Remove semantic badges, reasons, ranking weights, and tests from the
  suggestion path.
- Add theme-stage keyword subcategories using the deck's selected
  `archetype_tags`.
- Rank keyword cards higher when Moxfield inclusion is stronger, for example a
  card found in 5 relevant Moxfield decks ranks above a similar card found in 1.

Deferred:

- Removing the Qdrant Docker services, config folder, dependency, and startup
  client wiring. After this change they should no longer be needed by card
  suggestions, but the infrastructure cleanup can happen in a later pass.

## Current Behavior

The build wizard calls `POST /api/v1/decks/{deck_id}/build`. The backend builds
a stage query, embeds text, searches Qdrant, searches Postgres tags, searches
Postgres FTS, fetches EDHREC/Moxfield inclusion signals, and fuses all signals.
The theme stage currently uses the deck's selected archetype tags together, so
three selected tags produce one mixed result list.

Admin jobs also include embedding and Qdrant payload refresh steps:

- `embedding_service` creates vectors and upserts them into Qdrant.
- `tag_service.run_batch_tag` can sync tag payloads into Qdrant.
- Admin status exposes an `embed` job.

## Proposed Backend Design

### Retrieval

`retrieve_candidates` should become a structured retrieval function:

- Inputs no longer need `ai_client` or `qdrant_client`.
- Candidate discovery uses:
  - `_search_tags` for EDHREC-style tags and MTGJSON/card-derived tags.
  - `_search_fts` for text/name/oracle matches.
  - EDHREC commander recommendation inclusion.
  - EDHREC theme index inclusion for the active query tags.
  - Moxfield commander inclusion.
- The semantic result map is removed from candidate fusion.
- The `semantic` signal is removed from `signal_map`, source labels, highlight
  reasons, docs, and tests.
- Existing filters remain: color identity, existing deck cards, rejected cards,
  collection ownership, price bounds, stage land exclusion, type/subtype filters,
  avoid-card preferences, feedback weights, and user profile weights.

Scoring should reallocate former semantic weight to deterministic signals:

- Tag/representation overlap gets the largest share.
- EDHREC and Moxfield inclusion keep their explicit weights.
- FTS remains a secondary discovery/ranking signal.
- Type/subtype filters continue to act as strict filters when selected.
- `trusted_quota` still reserves room for EDHREC/Moxfield trusted cards.

### Theme Keyword Requests

Add `theme_tag: str | None` to `BuildRequest`.

In `ai_service.build_stage`:

- If `stage != "theme"`, behavior stays stage-based and can still use all deck
  archetype tags as ranking context.
- If `stage == "theme"` and the deck has `archetype_tags`, select the active tag:
  - Use `body.theme_tag` when it is present and included in the deck's
    `archetype_tags`.
  - Otherwise default to the first deck `archetype_tags` entry.
- Theme-stage `query_tags` should be the active theme tag first, plus only small
  fallback stage tags if needed to avoid empty discovery.
- Returned suggestions stay in the existing `BuildResponse` envelope.

This keeps pagination and filtering simple: switching keyword tabs resets
offset to `0`; load more continues within the active keyword.

### Pipeline And Admin Jobs

Remove the embedding job from the card-data pipeline:

- Stop calling `run_batch_embed` from refresh-all.
- Remove embed-specific admin endpoint/status slot or mark it unavailable only
  if an existing UI dependency requires a transition.
- Stop passing `qdrant_client` into tag sync; tags are stored in Postgres only.
- Remove Qdrant payload update code from `tag_service`.
- Keep MTGJSON keyword sync and EDHREC tag sync.

Do not remove Qdrant infrastructure in this implementation unless it becomes a
compile/runtime blocker. The later cleanup can delete Docker Qdrant services,
`qdrant-client`, `embedding_service`, Qdrant config, and startup initialization
once no remaining code imports them.

## Proposed Frontend Design

The build page already has one card grid per active stage. For the `theme` stage:

- Load the deck's `archetype_tags` from `getDeck`.
- Render a compact keyword selector above the suggestions grid when
  `activeStage === "theme"` and at least one tag exists.
- Default the selected theme keyword to the first tag.
- Send `theme_tag` in `apiClient.buildStage` calls for the theme stage.
- Changing the selected theme keyword invalidates/reloads only the theme stage.
- Keep the same card grid, accept/reject flow, type filters, price filters,
  collection filters, and load-more behavior.

Card source badges should no longer show `Semantic`. Cards can still show
`Tags`, `Text`, `EDHREC`, `EDHREC Theme`, `Moxfield`, and `Type`.

## API Contract

`BuildRequest` adds:

```python
theme_tag: str | None = Field(default=None, max_length=80)
```

`BuildResponse` does not change. The active keyword is frontend state derived
from the selected deck tag.

## Error Handling

- Invalid or unknown `theme_tag` values are ignored and replaced with the first
  selected deck keyword.
- Decks with no `archetype_tags` keep existing theme-stage fallback behavior.
- Empty retrieval results return an empty suggestion list, not an error.
- Qdrant being unavailable must not break build suggestions after this change.

## Testing

Backend:

- Update retrieval tests so candidates can be ranked without Qdrant or
  embeddings.
- Add a test that theme-stage `theme_tag` restricts/reranks suggestions for the
  selected tag.
- Add a test that an invalid `theme_tag` falls back to the first deck tag.
- Update admin job tests so refresh-all/tagging no longer require Qdrant payload
  sync or embedding.
- Update source/highlight tests to remove semantic expectations.

Frontend:

- Type-check `BuildRequest`/`buildStage` with `theme_tag`.
- Add or update tests if present for theme keyword selector behavior.

Manual verification:

- Run backend `uv run ruff check .`, `uv run ty check src/`, and `uv run pytest -q`.
- Run frontend lint/type checks according to existing package scripts.
- Build a deck with three archetype tags and verify the theme stage defaults to
  the first tag, then reloads distinct suggestions when the second and third
  tags are selected.

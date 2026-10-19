# API guide

Base path: `/api/v1`. FastAPI exposes the generated contract at `/openapi.json` and
interactive docs at `/docs` on the backend (`http://localhost:8000` locally).
Router and model source is authoritative; the table below is a navigation guide, not
a duplicate endpoint specification.

## Authentication

Application routes require `Authorization: Bearer <Google ID token>`. The frontend
proxy attaches it after Auth.js sign-in. Admin routes accept an allowlisted Google
account or `X-Internal-Token` for internal jobs. `/health` is outside `/api/v1` and
does not require sign-in. Discover also requires the account's `recommendations` capability.

## Route groups

Paths in this table are relative to `/api/v1`:

| Prefix/path | Main operations | Router source |
|---|---|---|
| `/cards` | Filtered local search, Scryfall-ID lookup, card sync | `routers/cards.py` |
| `/decks` | CRUD, text/URL import, cards/quantities/categories, plans, Community Picks and combos | `routers/decks.py` |
| `/decks/{deck_id}/build`, `/decks/{deck_id}/suggest` | Deterministic stage and prompt-based retrieval | `routers/ai.py` |
| `/decks/{deck_id}/coach`, `/decks/{deck_id}/coach/start` | Direct/background assistant turns; background progress via SSE | `routers/ai.py` |
| `/decks/{deck_id}/playtest`, `/decks/{deck_id}/mana-fix` | Simulation, analysis, gated optimizer, mana suggestions | `routers/ai.py` |
| `/decks/{deck_id}/export` | Moxfield text and buy lists | `routers/ai.py` |
| `/decks/{deck_id}/new-cards` | Read, explicitly analyze, dismiss/undo, plan | `routers/new_cards.py` |
| `/decks/{deck_id}/recommendations` | Discover status, local query previews, strategy drafts, runs, diagnostics and planning | `routers/recommendations.py` |
| `/me`, `/me/collections`, `/collections` | Current account and inventory/import/export | `routers/me.py`, `routers/collections.py` |
| `/decks/{deck_id}/snapshots`, `/snapshots`, `/decks/compare` | Saved deck snapshots and comparisons | `routers/snapshots.py` |
| `/decks/{deck_id}/revisions`, `/revisions` | Atomic planned-change application and history | `routers/revisions.py` |
| `/tags`, `/capabilities`, `/onboarding`, `/admin` | Catalogs, feature access, quickstart and maintenance | Corresponding files in `routers/` |

Router paths are relative to `backend/src/mtg_helper/`. No `/preferences`, `/me/preferences`,
`/me/ranking-weights`, `/decks/{deck_id}/coach/memory`, `/decks/{deck_id}/feedback`,
or `/decks/{deck_id}/chat` routes are registered.
Coach is the current chat interface.

## Examples

Create a deck with `POST /decks`:

```json
{
  "commander_scryfall_id": "00000000-0000-0000-0000-000000000001",
  "partner_scryfall_id": null,
  "name": "Token copies",
  "description": "Token copies and big X spells as finishers",
  "bracket": 3
}
```

The example UUID is a placeholder; use an ID from local card search.
Request a builder stage with `POST /decks/{deck_id}/build`:

```json
{"stage": "ramp", "target": 12, "offset": 0}
```

`BuildRequest` defines optional collection, price, type, subtype, theme, and exclusion
filters. It has no `action: next_stage` field. Stages are Theme, Ramp, Draw, Interaction,
and Lands, followed by Complete.

## Response conventions

Typed JSON successes generally use `DataResponse[T]`: `{"data": ..., "meta": ...}`.
Paginated responses include `total`, `limit`, and `offset`. Deletes can return 204;
exports and SSE use their own media types; some admin endpoints return job dictionaries.

`ErrorResponse` defines `{"error": {"code": "...", "message": "..."}}`, used by
application error handlers. Existing HTTP exceptions can instead use FastAPI's `detail`
wrapper, and request validation returns its validation-error structure. Do not assume every
current error already implements the intended envelope.

See the [New Cards](../../docs/new-cards-pilot-contract.md) and
[Discover](../../docs/recommendation-pilot-contract.md) contracts for paid-action and planning bounds.

"""Merge commander card-frequency evidence into owner-scoped Top Picks."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg

from mtg_helper.models.top_picks import (
    TopPickCard,
    TopPickSource,
    TopPickSourceSummary,
    TopPicksResponse,
)
from mtg_helper.services import (
    archidekt_commander_recs_service,
    collection_service,
    moxfield_recs_service,
)

_log = logging.getLogger(__name__)


class TopPicksNotFoundError(ValueError):
    """Raised when a deck does not exist or is not owned by the caller."""


@dataclass(slots=True)
class _SourceState:
    payload: dict[str, Any]
    fetched_at: datetime | None
    error: str | None = None

    @property
    def sample_size(self) -> int:
        return int(self.payload.get("sample_size") or len(self.payload.get("decks") or []))


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _owned_deck(
    conn: asyncpg.Connection,
    deck_id: UUID,
    email: str,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT d.id, d.commander_id, d.partner_id, c.name AS commander_name,
               c.color_identity AS commander_color_identity
        FROM decks d
        JOIN cards c ON c.id = d.commander_id
        WHERE d.id = $1 AND lower(d.owner_email) = $2
        """,
        deck_id,
        _normalize_email(email),
    )
    if row is None:
        raise TopPicksNotFoundError(f"Deck {deck_id} not found")
    return row


async def _refresh_source(
    refresh: Any,
    pool: asyncpg.Pool,
    commander_id: UUID,
) -> tuple[dict[str, Any], str | None]:
    try:
        return await refresh(pool, commander_id), None
    except Exception:
        _log.exception("Top Picks source refresh failed")
        return {}, "Source refresh failed"


async def _load_source_states(
    pool: asyncpg.Pool,
    commander_id: UUID,
) -> tuple[_SourceState, _SourceState]:
    (mox_payload, mox_error), (arch_payload, arch_error) = await asyncio.gather(
        _refresh_source(moxfield_recs_service.get_or_refresh, pool, commander_id),
        _refresh_source(archidekt_commander_recs_service.get_or_refresh, pool, commander_id),
    )
    async with pool.acquire() as conn:
        mox_row = await conn.fetchrow(
            "SELECT payload, fetched_at FROM moxfield_commander_recs WHERE commander_id = $1",
            commander_id,
        )
        arch_row = await conn.fetchrow(
            "SELECT payload, fetched_at FROM archidekt_commander_recs WHERE commander_id = $1",
            commander_id,
        )
    if not mox_payload and mox_row is not None:
        mox_payload = _plain_payload(mox_row["payload"])
    if not arch_payload and arch_row is not None:
        arch_payload = _plain_payload(arch_row["payload"])
    arch_error = arch_error or arch_payload.get("runtime_error")
    return (
        _SourceState(mox_payload, mox_row["fetched_at"] if mox_row else None, mox_error),
        _SourceState(arch_payload, arch_row["fetched_at"] if arch_row else None, arch_error),
    )


def _plain_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        import json

        return json.loads(payload)
    return {}


def _source_summary(
    source: Literal["moxfield", "archidekt"],
    state: _SourceState,
) -> TopPickSourceSummary:
    stale = bool(
        state.fetched_at
        and datetime.now(tz=UTC) - state.fetched_at
        >= archidekt_commander_recs_service.DEFAULT_MAX_AGE
    )
    error = state.error or state.payload.get("diagnostic")
    if state.sample_size == 0 and error is None:
        error = f"No matching {source.title()} commander decks found"
    return TopPickSourceSummary(
        source=source,
        deck_count=state.sample_size,
        fetched_at=state.fetched_at,
        stale=stale,
        error=error,
    )


async def _load_card_rows(
    conn: asyncpg.Connection,
    deck: asyncpg.Record,
    mox_payload: dict[str, Any],
    arch_payload: dict[str, Any],
) -> list[asyncpg.Record]:
    oracle_ids = list((mox_payload.get("by_oracle") or {}).keys())
    card_names = list((arch_payload.get("by_name") or {}).keys())
    if not oracle_ids and not card_names:
        return []
    excluded = [deck["commander_id"]]
    if deck["partner_id"] is not None:
        excluded.append(deck["partner_id"])
    return list(
        await conn.fetch(
            """
            SELECT c.id, c.scryfall_id, c.oracle_id, c.name,
                   c.mana_cost, c.type_line, c.image_uri,
                   CASE WHEN c.prices->>'eur' IS NULL THEN NULL
                        ELSE ROUND((c.prices->>'eur')::numeric * 100)::integer
                   END AS price_eur_cents,
                   COALESCE(dc.quantity, 0)::int AS physical_quantity,
                   p.direction AS plan_direction,
                   COALESCE(p.quantity, 0)::int AS planned_quantity
            FROM cards c
            LEFT JOIN deck_cards dc ON dc.deck_id = $1 AND dc.card_id = c.id
            LEFT JOIN deck_card_plans p ON p.deck_id = $1 AND p.card_id = c.id
            WHERE (c.oracle_id::text = ANY($2::text[]) OR lower(c.name) = ANY($3::text[]))
              AND c.is_canonical
              AND c.color_identity <@ $4::text[]
              AND c.legalities->>'commander' = 'legal'
              AND COALESCE(c.border_color, '') != 'gold'
              AND COALESCE(c.security_stamp, '') != 'acorn'
              AND c.type_line NOT LIKE '%Conspiracy%'
              AND c.id != ALL($5::uuid[])
            """,
            deck["id"],
            oracle_ids,
            card_names,
            list(deck["commander_color_identity"] or []),
            excluded,
        )
    )


def _combined_score(mox_rate: float, arch_rate: float, mox_ok: bool, arch_ok: bool) -> float:
    if mox_ok and arch_ok:
        consensus = 0.1 if mox_rate > 0 and arch_rate > 0 else 0.0
        return min(1.0, 0.45 * mox_rate + 0.45 * arch_rate + consensus)
    if mox_ok:
        return mox_rate
    if arch_ok:
        return arch_rate
    return 0.0


def _row_to_pick(
    row: asyncpg.Record,
    mox_state: _SourceState,
    arch_state: _SourceState,
) -> TopPickCard:
    oracle_id = str(row["oracle_id"]) if row["oracle_id"] else None
    mox_count = int((mox_state.payload.get("by_oracle") or {}).get(oracle_id, 0))
    arch_count = int((arch_state.payload.get("by_name") or {}).get(row["name"].casefold(), 0))
    mox_rate = mox_count / mox_state.sample_size if mox_state.sample_size else 0.0
    arch_rate = arch_count / arch_state.sample_size if arch_state.sample_size else 0.0
    return TopPickCard(
        card_id=row["id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        type_line=row["type_line"],
        image_uri=row["image_uri"],
        price_eur_cents=row["price_eur_cents"],
        combined_score=_combined_score(
            mox_rate,
            arch_rate,
            mox_state.sample_size > 0,
            arch_state.sample_size > 0,
        ),
        moxfield_count=mox_count,
        moxfield_sample_size=mox_state.sample_size,
        moxfield_rate=mox_rate,
        archidekt_count=arch_count,
        archidekt_sample_size=arch_state.sample_size,
        archidekt_rate=arch_rate,
        physical_quantity=row["physical_quantity"],
        plan_direction=row["plan_direction"],
        planned_quantity=row["planned_quantity"],
    )


def _filter_and_sort(picks: list[TopPickCard], source: TopPickSource) -> list[TopPickCard]:
    if source == "moxfield":
        picks = [pick for pick in picks if pick.moxfield_count > 0]
        return sorted(
            picks,
            key=lambda pick: (-pick.moxfield_rate, -pick.moxfield_count, pick.name.casefold()),
        )
    elif source == "archidekt":
        picks = [pick for pick in picks if pick.archidekt_count > 0]
        return sorted(
            picks,
            key=lambda pick: (
                -pick.archidekt_rate,
                -pick.archidekt_count,
                pick.name.casefold(),
            ),
        )
    return sorted(
        picks,
        key=lambda pick: (
            -pick.combined_score,
            -(int(pick.moxfield_count > 0) + int(pick.archidekt_count > 0)),
            -(pick.moxfield_count + pick.archidekt_count),
            pick.name.casefold(),
        ),
    )


async def get_top_picks(
    pool: asyncpg.Pool,
    deck_id: UUID,
    email: str,
    account_id: UUID,
    source: TopPickSource,
) -> TopPicksResponse:
    """Return merged source evidence with live deck, plan, and ownership state."""
    async with pool.acquire() as conn:
        deck = await _owned_deck(conn, deck_id, email)
    mox_state, arch_state = await _load_source_states(pool, deck["commander_id"])
    async with pool.acquire() as conn:
        rows = await _load_card_rows(conn, deck, mox_state.payload, arch_state.payload)
    picks = [_row_to_pick(row, mox_state, arch_state) for row in rows]
    ownership = await collection_service.build_ownership_map(
        pool, account_id, [pick.scryfall_id for pick in picks]
    )
    for pick in picks:
        pick.owned_in = ownership.get(pick.scryfall_id, [])
    return TopPicksResponse(
        commander_name=deck["commander_name"],
        source=source,
        sources=[
            _source_summary("moxfield", mox_state),
            _source_summary("archidekt", arch_state),
        ],
        picks=_filter_and_sort(picks, source),
    )

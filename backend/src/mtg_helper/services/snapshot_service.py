"""Deck snapshot service: point-in-time deck copies + composition diffing."""

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.snapshots import (
    ComparisonSideMeta,
    DeckCompareResponse,
    DeckDiff,
    DiffCardInfo,
    DiffEntry,
    SnapshotCardItem,
    SnapshotDetailResponse,
    SnapshotResponse,
    SnapshotSummary,
)

_log = logging.getLogger(__name__)


class SnapshotNotFoundError(ValueError):
    """Raised when a snapshot does not exist or is not owned by the caller."""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _parse_stage_targets(raw: Any) -> dict[str, int]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


async def _assert_deck_owner(conn: asyncpg.Connection, deck_id: UUID, email: str) -> None:
    row = await conn.fetchrow(
        "SELECT lower(owner_email) AS owner FROM decks WHERE id = $1", deck_id
    )
    if row is None or row["owner"] != _normalize_email(email):
        raise SnapshotNotFoundError(f"Deck {deck_id} not found")


async def _resolve_snapshot_owner(
    conn: asyncpg.Connection, snapshot_id: UUID
) -> tuple[UUID, str | None]:
    """Return (deck_id, owner_email_lower) for a snapshot, or raise if missing."""
    row = await conn.fetchrow(
        """
        SELECT s.deck_id, lower(d.owner_email) AS owner
        FROM deck_snapshots s
        JOIN decks d ON d.id = s.deck_id
        WHERE s.id = $1
        """,
        snapshot_id,
    )
    if row is None:
        raise SnapshotNotFoundError(f"Snapshot {snapshot_id} not found")
    return row["deck_id"], row["owner"]


async def _assert_snapshot_owner(conn: asyncpg.Connection, snapshot_id: UUID, email: str) -> UUID:
    deck_id, owner = await _resolve_snapshot_owner(conn, snapshot_id)
    if owner != _normalize_email(email):
        raise SnapshotNotFoundError(f"Snapshot {snapshot_id} not found")
    return deck_id


def _row_to_summary(row: asyncpg.Record) -> SnapshotSummary:
    return SnapshotSummary(
        id=row["id"],
        deck_id=row["deck_id"],
        label=row["label"],
        source=row["source"],
        stage=row["stage"],
        deck_name=row["deck_name"],
        bracket=row["bracket"],
        card_count=row["card_count"] or 0,
        created_at=row["created_at"],
    )


def _row_to_response(row: asyncpg.Record) -> SnapshotResponse:
    return SnapshotResponse(
        id=row["id"],
        deck_id=row["deck_id"],
        label=row["label"],
        source=row["source"],
        stage=row["stage"],
        deck_name=row["deck_name"],
        bracket=row["bracket"],
        stage_targets=_parse_stage_targets(row["stage_targets"]),
        archetype_tags=list(row["archetype_tags"] or []),
        created_at=row["created_at"],
    )


def _row_to_card(row: asyncpg.Record) -> SnapshotCardItem:
    return SnapshotCardItem(
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        color_identity=list(row["color_identity"] or []),
        image_uri=row["image_uri"],
        quantity=row["quantity"],
        categories=list(row["categories"] or []),
        added_by=row["added_by"],
        ai_reasoning=row["ai_reasoning"],
    )


async def _insert_snapshot(
    conn: asyncpg.Connection,
    deck_id: UUID,
    *,
    label: str | None,
    source: str,
) -> asyncpg.Record:
    """Insert a snapshot row from current deck state. Caller must own the deck."""
    deck_row = await conn.fetchrow(
        "SELECT name, stage, bracket, stage_targets, archetype_tags FROM decks WHERE id = $1",
        deck_id,
    )
    if deck_row is None:
        raise SnapshotNotFoundError(f"Deck {deck_id} not found")
    snapshot_row = await conn.fetchrow(
        """
        INSERT INTO deck_snapshots
            (deck_id, label, source, stage, deck_name, bracket, stage_targets, archetype_tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        deck_id,
        label,
        source,
        deck_row["stage"],
        deck_row["name"],
        deck_row["bracket"],
        json.dumps(_parse_stage_targets(deck_row["stage_targets"])),
        list(deck_row["archetype_tags"] or []),
    )
    await conn.execute(
        """
        INSERT INTO deck_snapshot_cards
            (snapshot_id, card_id, quantity, categories, added_by, ai_reasoning)
        SELECT $1, card_id, quantity, categories, added_by, ai_reasoning
        FROM deck_cards
        WHERE deck_id = $2
        """,
        snapshot_row["id"],
        deck_id,
    )
    return snapshot_row


async def create_snapshot(
    pool: asyncpg.Pool,
    deck_id: UUID,
    *,
    label: str | None,
    source: str,
    email: str,
) -> SnapshotResponse:
    """Create a snapshot of a deck's current composition.

    Args:
        pool: asyncpg connection pool.
        deck_id: Deck UUID to snapshot.
        label: Optional user-supplied label. Auto-snapshots may pass a synthesized label.
        source: 'manual' or 'auto_stage'.
        email: Owner email for authorization.

    Returns:
        SnapshotResponse with snapshot metadata.

    Raises:
        SnapshotNotFoundError: deck missing or not owned by ``email``.
    """
    async with pool.acquire() as conn, conn.transaction():
        await _assert_deck_owner(conn, deck_id, email)
        row = await _insert_snapshot(conn, deck_id, label=label, source=source)
    return _row_to_response(row)


async def create_auto_snapshot(
    pool: asyncpg.Pool,
    deck_id: UUID,
    *,
    new_stage: str,
) -> SnapshotResponse | None:
    """Create an automatic stage-advance snapshot. Best-effort; returns None on failure.

    Owner check is skipped — caller has already authorized the underlying update.
    """
    try:
        async with pool.acquire() as conn, conn.transaction():
            row = await _insert_snapshot(
                conn, deck_id, label=f"entered {new_stage}", source="auto_stage"
            )
        return _row_to_response(row)
    except Exception:
        _log.exception("Auto-snapshot failed for deck %s entering stage %s", deck_id, new_stage)
        return None


async def list_snapshots(
    pool: asyncpg.Pool,
    deck_id: UUID,
    *,
    email: str,
) -> list[SnapshotSummary]:
    """List snapshots for a deck, newest first."""
    async with pool.acquire() as conn:
        await _assert_deck_owner(conn, deck_id, email)
        rows = await conn.fetch(
            """
            SELECT s.id, s.deck_id, s.label, s.source, s.stage, s.deck_name, s.bracket,
                   s.created_at,
                   COALESCE((SELECT SUM(quantity) FROM deck_snapshot_cards c
                             WHERE c.snapshot_id = s.id), 0) AS card_count
            FROM deck_snapshots s
            WHERE s.deck_id = $1
            ORDER BY s.created_at DESC
            """,
            deck_id,
        )
    return [_row_to_summary(r) for r in rows]


async def get_snapshot(
    pool: asyncpg.Pool,
    snapshot_id: UUID,
    *,
    email: str,
) -> SnapshotDetailResponse:
    """Fetch a snapshot with full card list."""
    async with pool.acquire() as conn:
        await _assert_snapshot_owner(conn, snapshot_id, email)
        snapshot_row = await conn.fetchrow(
            "SELECT * FROM deck_snapshots WHERE id = $1", snapshot_id
        )
        card_rows = await conn.fetch(
            """
            SELECT sc.card_id, sc.quantity, sc.categories, sc.added_by, sc.ai_reasoning,
                   c.scryfall_id, c.name, c.mana_cost, c.cmc, c.type_line,
                   c.color_identity, c.image_uri
            FROM deck_snapshot_cards sc
            JOIN cards c ON c.id = sc.card_id
            WHERE sc.snapshot_id = $1
            ORDER BY c.name
            """,
            snapshot_id,
        )
    assert snapshot_row is not None  # owner check above guarantees existence
    return SnapshotDetailResponse(
        id=snapshot_row["id"],
        deck_id=snapshot_row["deck_id"],
        label=snapshot_row["label"],
        source=snapshot_row["source"],
        stage=snapshot_row["stage"],
        deck_name=snapshot_row["deck_name"],
        bracket=snapshot_row["bracket"],
        stage_targets=_parse_stage_targets(snapshot_row["stage_targets"]),
        archetype_tags=list(snapshot_row["archetype_tags"] or []),
        created_at=snapshot_row["created_at"],
        cards=[_row_to_card(r) for r in card_rows],
    )


async def delete_snapshot(
    pool: asyncpg.Pool,
    snapshot_id: UUID,
    *,
    email: str,
) -> None:
    """Delete a snapshot. Owner-scoped."""
    async with pool.acquire() as conn:
        await _assert_snapshot_owner(conn, snapshot_id, email)
        await conn.execute("DELETE FROM deck_snapshots WHERE id = $1", snapshot_id)


# ----- Comparison ----------------------------------------------------------


class _Composition:
    """In-memory representation of one side of a diff."""

    def __init__(
        self,
        *,
        kind: str,
        side_id: UUID,
        deck_id: UUID,
        deck_name: str,
        label: str | None,
        stage: str,
        bracket: int | None,
        cards: dict[UUID, dict[str, Any]],
    ) -> None:
        self.kind = kind
        self.side_id = side_id
        self.deck_id = deck_id
        self.deck_name = deck_name
        self.label = label
        self.stage = stage
        self.bracket = bracket
        self.cards = cards

    def card_count(self) -> int:
        return sum(int(v["quantity"]) for v in self.cards.values())

    def meta(self) -> ComparisonSideMeta:
        return ComparisonSideMeta(
            kind="snapshot" if self.kind == "snapshot" else "deck",
            id=self.side_id,
            deck_id=self.deck_id,
            deck_name=self.deck_name,
            label=self.label,
            stage=self.stage,
            bracket=self.bracket,
            card_count=self.card_count(),
        )


async def _load_deck_composition(
    conn: asyncpg.Connection, deck_id: UUID, email: str
) -> _Composition:
    deck_row = await conn.fetchrow(
        "SELECT id, name, stage, bracket, lower(owner_email) AS owner FROM decks WHERE id = $1",
        deck_id,
    )
    if deck_row is None or deck_row["owner"] != _normalize_email(email):
        raise SnapshotNotFoundError(f"Deck {deck_id} not found")
    card_rows = await conn.fetch(
        """
        SELECT dc.card_id, dc.quantity, dc.categories,
               c.scryfall_id, c.name, c.mana_cost, c.cmc, c.type_line,
               c.image_uri, c.color_identity
        FROM deck_cards dc
        JOIN cards c ON c.id = dc.card_id
        WHERE dc.deck_id = $1
        """,
        deck_id,
    )
    cards = {r["card_id"]: dict(r) for r in card_rows}
    return _Composition(
        kind="deck",
        side_id=deck_id,
        deck_id=deck_id,
        deck_name=deck_row["name"],
        label=None,
        stage=deck_row["stage"],
        bracket=deck_row["bracket"],
        cards=cards,
    )


async def _load_snapshot_composition(
    conn: asyncpg.Connection, snapshot_id: UUID, email: str
) -> _Composition:
    snapshot_row = await conn.fetchrow(
        """
        SELECT s.id, s.deck_id, s.label, s.stage, s.deck_name, s.bracket,
               lower(d.owner_email) AS owner
        FROM deck_snapshots s
        JOIN decks d ON d.id = s.deck_id
        WHERE s.id = $1
        """,
        snapshot_id,
    )
    if snapshot_row is None or snapshot_row["owner"] != _normalize_email(email):
        raise SnapshotNotFoundError(f"Snapshot {snapshot_id} not found")
    card_rows = await conn.fetch(
        """
        SELECT sc.card_id, sc.quantity, sc.categories,
               c.scryfall_id, c.name, c.mana_cost, c.cmc, c.type_line,
               c.image_uri, c.color_identity
        FROM deck_snapshot_cards sc
        JOIN cards c ON c.id = sc.card_id
        WHERE sc.snapshot_id = $1
        """,
        snapshot_id,
    )
    cards = {r["card_id"]: dict(r) for r in card_rows}
    return _Composition(
        kind="snapshot",
        side_id=snapshot_id,
        deck_id=snapshot_row["deck_id"],
        deck_name=snapshot_row["deck_name"],
        label=snapshot_row["label"],
        stage=snapshot_row["stage"],
        bracket=snapshot_row["bracket"],
        cards=cards,
    )


def _card_info(row: dict[str, Any]) -> DiffCardInfo:
    return DiffCardInfo(
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row.get("mana_cost"),
        cmc=row.get("cmc"),
        type_line=row.get("type_line"),
        image_uri=row.get("image_uri"),
        color_identity=list(row.get("color_identity") or []),
    )


def diff_compositions(
    left: dict[UUID, dict[str, Any]],
    right: dict[UUID, dict[str, Any]],
) -> DeckDiff:
    """Compare two card-id-keyed compositions and bucket the differences.

    Each value must have at least: card_id, scryfall_id, name, quantity, categories.
    """
    added: list[DiffEntry] = []
    removed: list[DiffEntry] = []
    quantity_changed: list[DiffEntry] = []
    common: list[DiffEntry] = []

    all_ids = set(left.keys()) | set(right.keys())
    for cid in sorted(all_ids, key=lambda x: str(x)):
        lrow = left.get(cid)
        rrow = right.get(cid)
        source_row = rrow if rrow is not None else lrow
        assert source_row is not None  # at least one side has the card
        info = _card_info(source_row)
        lqty = int(lrow["quantity"]) if lrow else 0
        rqty = int(rrow["quantity"]) if rrow else 0
        lcats = list(lrow.get("categories") or []) if lrow else []
        rcats = list(rrow.get("categories") or []) if rrow else []
        entry = DiffEntry(
            card=info,
            left_quantity=lqty,
            right_quantity=rqty,
            left_categories=lcats,
            right_categories=rcats,
        )
        if lrow is None:
            added.append(entry)
        elif rrow is None:
            removed.append(entry)
        elif lqty != rqty:
            quantity_changed.append(entry)
        else:
            common.append(entry)

    sort_key = lambda e: e.card.name.lower()  # noqa: E731
    return DeckDiff(
        added=sorted(added, key=sort_key),
        removed=sorted(removed, key=sort_key),
        quantity_changed=sorted(quantity_changed, key=sort_key),
        common=sorted(common, key=sort_key),
    )


async def compare(
    pool: asyncpg.Pool,
    *,
    left_kind: str,
    left_id: UUID,
    right_kind: str,
    right_id: UUID,
    email: str,
) -> DeckCompareResponse:
    """Diff two compositions. Each side may be a live deck or a snapshot."""
    async with pool.acquire() as conn:
        if left_kind == "snapshot":
            left = await _load_snapshot_composition(conn, left_id, email)
        else:
            left = await _load_deck_composition(conn, left_id, email)
        if right_kind == "snapshot":
            right = await _load_snapshot_composition(conn, right_id, email)
        else:
            right = await _load_deck_composition(conn, right_id, email)

    diff = diff_compositions(left.cards, right.cards)
    return DeckCompareResponse(left=left.meta(), right=right.meta(), diff=diff)

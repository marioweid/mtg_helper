"""Collection CRUD, CSV import/export, and printing resolution."""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CollectionMembership
from mtg_helper.models.collections import (
    CollectionCardAdd,
    CollectionCardItem,
    CollectionCardUpdate,
    CollectionImportResponse,
    CollectionResponse,
)
from mtg_helper.services import card_service

_log = logging.getLogger(__name__)

_MOXFIELD_HEADERS: tuple[str, ...] = (
    "Count",
    "Tradelist Count",
    "Name",
    "Edition",
    "Condition",
    "Language",
    "Foil",
    "Tags",
    "Last Modified",
    "Collector Number",
    "Alter",
    "Proxy",
    "Purchase Price",
)


class CollectionNotFoundError(ValueError):
    """Raised when a collection does not exist."""


class AccountNotFoundError(ValueError):
    """Raised when the referenced account does not exist."""


class DuplicateCollectionNameError(ValueError):
    """Raised when a collection name already exists for the account."""


class CardNotFoundError(ValueError):
    """Raised when a Scryfall ID does not resolve to a card in the local DB."""


@dataclass
class ParsedCollectionRow:
    """A normalized row parsed from a supported collection CSV."""

    name: str
    quantity: int
    set_code: str
    collector_number: str
    foil: bool
    condition: str | None
    language: str | None
    tags: list[str]
    purchase_price: Decimal | None
    last_modified: datetime | None
    scryfall_id: UUID | None = None


def _parse_int(value: str, default: int = 1) -> int:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def _parse_bool(value: str) -> bool:
    """Parse common CSV boolean and foil markers."""
    v = (value or "").strip().lower()
    return v in {"true", "foil", "etched", "1", "yes"}


def _parse_uuid(value: str) -> UUID | None:
    stripped = (value or "").strip()
    if not stripped:
        return None
    try:
        return UUID(stripped)
    except ValueError:
        return None


def _parse_price(value: str) -> Decimal | None:
    stripped = (value or "").strip()
    if not stripped:
        return None
    try:
        return Decimal(stripped)
    except InvalidOperation:
        return None


def _parse_datetime(value: str) -> datetime | None:
    stripped = (value or "").strip()
    if not stripped:
        return None
    try:
        return datetime.fromisoformat(stripped)
    except ValueError:
        return None


def _parse_tags(value: str) -> list[str]:
    """Moxfield joins tags with commas; split + strip, drop empties."""
    if not value:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


def parse_moxfield_csv(text: str) -> list[ParsedCollectionRow]:
    """Parse a Moxfield-exported CSV into collection rows.

    Accepts the standard Moxfield export header. Unknown columns are ignored.
    Blank `Count` rows and header-only input raise ValueError.

    Args:
        text: Raw CSV text pasted by the user.

    Returns:
        List of parsed rows; empty only when input is malformed.

    Raises:
        ValueError: If the CSV cannot be parsed or contains no data rows.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV is empty or missing header row.")

    if "Name" not in reader.fieldnames or "Count" not in reader.fieldnames:
        raise ValueError("CSV must include at least 'Count' and 'Name' columns.")

    rows: list[ParsedCollectionRow] = []
    for raw in reader:
        name = (raw.get("Name") or "").strip()
        if not name:
            continue
        quantity = _parse_int(raw.get("Count") or "", default=1)
        if quantity <= 0:
            continue
        rows.append(
            ParsedCollectionRow(
                name=name,
                quantity=quantity,
                set_code=(raw.get("Edition") or "").strip(),
                collector_number=(raw.get("Collector Number") or "").strip(),
                foil=_parse_bool(raw.get("Foil") or ""),
                condition=(raw.get("Condition") or "").strip() or None,
                language=(raw.get("Language") or "").strip() or None,
                tags=_parse_tags(raw.get("Tags") or ""),
                purchase_price=_parse_price(raw.get("Purchase Price") or ""),
                last_modified=_parse_datetime(raw.get("Last Modified") or ""),
            )
        )

    if not rows:
        raise ValueError("CSV contained no valid card rows.")
    return rows


def parse_manabox_csv(text: str) -> list[ParsedCollectionRow]:
    """Parse a ManaBox-exported CSV into normalized collection rows.

    Args:
        text: Raw ManaBox CSV text pasted or uploaded by the user.

    Returns:
        Parsed collection rows.

    Raises:
        ValueError: If required headers are missing or no valid rows exist.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("ManaBox CSV is empty or missing a header row.")
    required = {"Name", "Quantity"}
    if not required.issubset(reader.fieldnames):
        raise ValueError("ManaBox CSV must include 'Name' and 'Quantity' columns.")

    rows: list[ParsedCollectionRow] = []
    for raw in reader:
        name = (raw.get("Name") or "").strip()
        if not name:
            continue
        quantity = _parse_int(raw.get("Quantity") or "", default=1)
        if quantity <= 0:
            continue
        rows.append(
            ParsedCollectionRow(
                name=name,
                quantity=quantity,
                set_code=(raw.get("Set code") or "").strip(),
                collector_number=(raw.get("Collector number") or "").strip(),
                foil=_parse_bool(raw.get("Foil") or ""),
                condition=(raw.get("Condition") or "").strip() or None,
                language=(raw.get("Language") or "").strip() or None,
                tags=[],
                purchase_price=None,
                last_modified=None,
                scryfall_id=_parse_uuid(raw.get("Scryfall ID") or ""),
            )
        )

    if not rows:
        raise ValueError("ManaBox CSV contained no valid card rows.")
    return rows


def parse_collection_csv(text: str, csv_format: str) -> list[ParsedCollectionRow]:
    """Dispatch CSV parsing to the explicitly selected collection format."""
    if csv_format == "moxfield":
        return parse_moxfield_csv(text)
    if csv_format == "manabox":
        return parse_manabox_csv(text)
    raise ValueError(f"Unsupported collection CSV format: {csv_format}")


async def _assert_account_exists(conn: asyncpg.Connection, account_id: UUID) -> None:
    row = await conn.fetchrow("SELECT 1 FROM accounts WHERE id = $1", account_id)
    if row is None:
        raise AccountNotFoundError(f"Account {account_id} not found")


async def _card_count(conn: asyncpg.Connection, collection_id: UUID) -> int:
    """Sum `quantity` across all rows in a collection."""
    result = await conn.fetchval(
        "SELECT COALESCE(SUM(quantity), 0)::int FROM collection_cards WHERE collection_id = $1",
        collection_id,
    )
    return int(result or 0)


def _row_to_collection(row: asyncpg.Record, card_count: int) -> CollectionResponse:
    return CollectionResponse(
        id=row["id"],
        account_id=row["account_id"],
        name=row["name"],
        card_count=card_count,
        created_at=row["created_at"],
    )


async def create_collection(pool: asyncpg.Pool, account_id: UUID, name: str) -> CollectionResponse:
    """Create a new collection for an account.

    Args:
        pool: asyncpg connection pool.
        account_id: Owner account UUID.
        name: Human-readable collection name (unique per account).

    Returns:
        The created collection.

    Raises:
        AccountNotFoundError: If the account does not exist.
        DuplicateCollectionNameError: If the account already has a collection with this name.
    """
    async with pool.acquire() as conn:
        await _assert_account_exists(conn, account_id)
        try:
            row = await conn.fetchrow(
                "INSERT INTO collections (account_id, name) VALUES ($1, $2) RETURNING *",
                account_id,
                name,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateCollectionNameError(
                f"Account {account_id} already has a collection named '{name}'"
            ) from exc
    return _row_to_collection(row, card_count=0)


async def list_collections(pool: asyncpg.Pool, account_id: UUID) -> list[CollectionResponse]:
    """List all collections for an account, ordered newest-first."""
    async with pool.acquire() as conn:
        await _assert_account_exists(conn, account_id)
        rows = await conn.fetch(
            """
            SELECT c.*,
                   COALESCE(
                       (SELECT SUM(quantity) FROM collection_cards WHERE collection_id = c.id),
                       0
                   )::int AS card_count
            FROM collections c
            WHERE c.account_id = $1
            ORDER BY c.created_at DESC
            """,
            account_id,
        )
    return [_row_to_collection(r, r["card_count"]) for r in rows]


async def get_collection(pool: asyncpg.Pool, collection_id: UUID) -> CollectionResponse:
    """Fetch a single collection by ID.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM collections WHERE id = $1", collection_id)
        if row is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")
        count = await _card_count(conn, collection_id)
    return _row_to_collection(row, count)


async def rename_collection(
    pool: asyncpg.Pool, collection_id: UUID, name: str
) -> CollectionResponse:
    """Rename a collection.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
        DuplicateCollectionNameError: If the new name collides with another collection
            for the same account.
    """
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "UPDATE collections SET name = $2 WHERE id = $1 RETURNING *",
                collection_id,
                name,
            )
        except asyncpg.UniqueViolationError as exc:
            raise DuplicateCollectionNameError(
                f"A collection named '{name}' already exists for this account"
            ) from exc
        if row is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")
        count = await _card_count(conn, collection_id)
    return _row_to_collection(row, count)


async def delete_collection(pool: asyncpg.Pool, collection_id: UUID) -> bool:
    """Delete a collection and all its cards (cascade).

    Returns:
        True if deleted, False if not found.
    """
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM collections WHERE id = $1", collection_id)
    return result == "DELETE 1"


def _row_to_card_item(row: asyncpg.Record) -> CollectionCardItem:
    return CollectionCardItem(
        card_id=row["card_id"],
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        set_code=row["set_code"],
        collector_number=row["collector_number"],
        image_uri=row["image_uri"],
        color_identity=list(row["color_identity"] or []),
        type_line=row["type_line"],
        quantity=row["quantity"],
        foil=row["foil"],
        condition=row["condition"],
        language=row["language"],
        tags=list(row["tags"] or []),
        purchase_price=row["purchase_price"],
        last_modified=row["last_modified"],
    )


async def list_cards(
    pool: asyncpg.Pool,
    collection_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    type_filter: str | None = None,
    min_price_cents: int | None = None,
    max_price_cents: int | None = None,
    search: str | None = None,
    sort: str = "name",
    direction: str = "asc",
    group: str = "none",
) -> tuple[list[CollectionCardItem], int]:
    """List cards in a collection with pagination and optional filters.

    Args:
        pool: asyncpg connection pool.
        collection_id: Collection UUID.
        limit: Max rows per page.
        offset: Pagination offset.
        type_filter: Optional case-insensitive substring of ``cards.type_line``.
        min_price_cents: Optional inclusive lower bound on Scryfall EUR price (cents).
        max_price_cents: Optional inclusive upper bound on Scryfall EUR price (cents).
            When either price bound is set, cards without an EUR price are excluded.
        search: Optional case-insensitive card-name substring.
        sort: Sort field: name, price, or quantity.
        direction: Sort direction: ascending or descending.
        group: Leading grouping order: none, primary type, or set code.

    Returns:
        Tuple of (items, total count) reflecting the filtered set.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
    """
    filter_sql, filter_params = _build_collection_card_filter(
        type_filter, min_price_cents, max_price_cents, search
    )
    order_sql = _collection_card_order(sort, direction, group)
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM collections WHERE id = $1", collection_id)
        if exists is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        base_params: list[object] = [collection_id, *filter_params]
        list_params = [*base_params, limit, offset]
        rows = await conn.fetch(
            f"""
            SELECT cc.card_id, cc.set_code, cc.collector_number, cc.quantity, cc.foil,
                   cc.condition, cc.language, cc.tags, cc.purchase_price, cc.last_modified,
                   c.scryfall_id, c.name, c.image_uri, c.color_identity, c.type_line
            FROM collection_cards cc
            JOIN cards c ON cc.card_id = c.id
            WHERE cc.collection_id = $1{filter_sql}
            ORDER BY {order_sql}
            LIMIT ${len(base_params) + 1} OFFSET ${len(base_params) + 2}
            """,
            *list_params,
        )
        total: int = await conn.fetchval(
            f"""
            SELECT count(*)
            FROM collection_cards cc
            JOIN cards c ON cc.card_id = c.id
            WHERE cc.collection_id = $1{filter_sql}
            """,
            *base_params,
        )
    return [_row_to_card_item(r) for r in rows], total


def _build_collection_card_filter(
    type_filter: str | None,
    min_price_cents: int | None,
    max_price_cents: int | None,
    search: str | None,
) -> tuple[str, list[object]]:
    """Build the WHERE-clause fragment + params for collection card filters.

    Param positions are anchored to ``$2..`` since the caller uses ``$1`` for
    the collection_id.
    """
    clauses: list[str] = []
    params: list[object] = []
    next_pos = 2
    if search and search.strip():
        params.append(f"%{search.strip()}%")
        clauses.append(f"AND c.name ILIKE ${next_pos}")
        next_pos += 1
    if type_filter:
        params.append(f"%{type_filter}%")
        clauses.append(f"AND c.type_line ILIKE ${next_pos}")
        next_pos += 1
    if min_price_cents is not None or max_price_cents is not None:
        clauses.append("AND (c.prices->>'eur') IS NOT NULL")
        if min_price_cents is not None:
            params.append(min_price_cents)
            clauses.append(f"AND ((c.prices->>'eur')::numeric * 100) >= ${next_pos}")
            next_pos += 1
        if max_price_cents is not None:
            params.append(max_price_cents)
            clauses.append(f"AND ((c.prices->>'eur')::numeric * 100) <= ${next_pos}")
            next_pos += 1
    return (" " + " ".join(clauses) if clauses else ""), params


_PRIMARY_TYPE_SQL = """CASE
    WHEN c.type_line ILIKE '%Creature%' THEN 'Creature'
    WHEN c.type_line ILIKE '%Instant%' THEN 'Instant'
    WHEN c.type_line ILIKE '%Sorcery%' THEN 'Sorcery'
    WHEN c.type_line ILIKE '%Artifact%' THEN 'Artifact'
    WHEN c.type_line ILIKE '%Enchantment%' THEN 'Enchantment'
    WHEN c.type_line ILIKE '%Planeswalker%' THEN 'Planeswalker'
    WHEN c.type_line ILIKE '%Battle%' THEN 'Battle'
    WHEN c.type_line ILIKE '%Land%' THEN 'Land'
    ELSE 'Other'
END"""


def _collection_card_order(sort: str, direction: str, group: str) -> str:
    """Return an allowlisted ORDER BY fragment for collection pagination."""
    sort_expressions = {
        "name": "lower(c.name)",
        "price": "((c.prices->>'eur')::numeric)",
        "quantity": "cc.quantity",
    }
    group_expressions = {
        "none": None,
        "type": _PRIMARY_TYPE_SQL,
        "set": "upper(COALESCE(NULLIF(cc.set_code, ''), 'Unknown Set'))",
    }
    sort_expression = sort_expressions.get(sort, sort_expressions["name"])
    group_expression = group_expressions.get(group)
    order_direction = "DESC" if direction == "desc" else "ASC"
    parts = [f"{sort_expression} {order_direction} NULLS LAST"]
    if group_expression:
        parts.insert(0, f"{group_expression} ASC")
    parts.extend(
        [
            "lower(c.name) ASC",
            "cc.card_id ASC",
            "cc.set_code ASC",
            "cc.collector_number ASC",
            "cc.foil ASC",
        ]
    )
    return ", ".join(parts)


async def _resolve_add_target(pool: asyncpg.Pool, data: CollectionCardAdd) -> UUID:
    """Resolve the target card_id from either scryfall_id or name on the add request.

    Raises:
        CardNotFoundError: If neither identifier matches a card in the local DB.
    """
    if data.scryfall_id is not None:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM cards WHERE scryfall_id = $1", data.scryfall_id
            )
        if row is None:
            raise CardNotFoundError(f"Card with Scryfall ID {data.scryfall_id} not found")
        return row["id"]

    assert data.name is not None
    card = await card_service.resolve_card_by_name(pool, data.name)
    if card is None:
        raise CardNotFoundError(f"No card found matching name '{data.name}'")
    return card.id


async def add_card(
    pool: asyncpg.Pool, collection_id: UUID, data: CollectionCardAdd
) -> CollectionCardItem:
    """Add a single card (one printing) to a collection via scryfall_id or name.

    Upserts on (collection_id, card_id, set_code, collector_number, foil):
    incrementing quantity if the row already exists.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
        CardNotFoundError: If the scryfall_id or name cannot be resolved.
    """
    card_id = await _resolve_add_target(pool, data)
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM collections WHERE id = $1", collection_id)
        if exists is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        await conn.execute(
            """
            INSERT INTO collection_cards (
                collection_id, card_id, set_code, collector_number, foil,
                quantity, condition, language, tags, purchase_price, last_modified
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
            ON CONFLICT (collection_id, card_id, set_code, collector_number, foil)
            DO UPDATE SET
                quantity       = collection_cards.quantity + EXCLUDED.quantity,
                condition      = COALESCE(EXCLUDED.condition, collection_cards.condition),
                language       = COALESCE(EXCLUDED.language, collection_cards.language),
                tags           = EXCLUDED.tags,
                purchase_price = COALESCE(EXCLUDED.purchase_price, collection_cards.purchase_price),
                last_modified  = now()
            """,
            collection_id,
            card_id,
            data.set_code,
            data.collector_number,
            data.foil,
            data.quantity,
            data.condition,
            data.language,
            data.tags,
            data.purchase_price,
        )
        row = await conn.fetchrow(
            """
            SELECT cc.card_id, cc.set_code, cc.collector_number, cc.quantity, cc.foil,
                   cc.condition, cc.language, cc.tags, cc.purchase_price, cc.last_modified,
                   c.scryfall_id, c.name, c.image_uri, c.color_identity, c.type_line
            FROM collection_cards cc
            JOIN cards c ON cc.card_id = c.id
            WHERE cc.collection_id = $1 AND cc.card_id = $2
              AND cc.set_code = $3 AND cc.collector_number = $4 AND cc.foil = $5
            """,
            collection_id,
            card_id,
            data.set_code,
            data.collector_number,
            data.foil,
        )
    return _row_to_card_item(row)


async def update_card(
    pool: asyncpg.Pool,
    collection_id: UUID,
    card_id: UUID,
    data: CollectionCardUpdate,
) -> CollectionCardItem | None:
    """Patch a collection card. Matches by card_id only (first printing row).

    Returns the updated row, or None if no matching row exists.
    """
    updates = data.model_dump(exclude_none=True)
    if not updates:
        async with pool.acquire() as conn:
            row = await _fetch_first_printing(conn, collection_id, card_id)
        return _row_to_card_item(row) if row else None

    fields = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(updates))
    values = list(updates.values())
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            UPDATE collection_cards SET {fields}, last_modified = now()
            WHERE collection_id = $1 AND card_id = $2
            """,
            collection_id,
            card_id,
            *values,
        )
        row = await _fetch_first_printing(conn, collection_id, card_id)
    return _row_to_card_item(row) if row else None


async def _fetch_first_printing(
    conn: asyncpg.Connection, collection_id: UUID, card_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT cc.card_id, cc.set_code, cc.collector_number, cc.quantity, cc.foil,
               cc.condition, cc.language, cc.tags, cc.purchase_price, cc.last_modified,
               c.scryfall_id, c.name, c.image_uri, c.color_identity, c.type_line
        FROM collection_cards cc
        JOIN cards c ON cc.card_id = c.id
        WHERE cc.collection_id = $1 AND cc.card_id = $2
        ORDER BY cc.set_code, cc.collector_number, cc.foil
        LIMIT 1
        """,
        collection_id,
        card_id,
    )


async def remove_card(pool: asyncpg.Pool, collection_id: UUID, card_id: UUID) -> bool:
    """Remove all printings of a card from a collection.

    Returns:
        True if any rows were removed, False otherwise.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM collection_cards WHERE collection_id = $1 AND card_id = $2",
            collection_id,
            card_id,
        )
    return result != "DELETE 0"


async def get_owned_card_ids(pool: asyncpg.Pool, collection_id: UUID) -> frozenset[UUID]:
    """Return the distinct `cards.id` values owned in a collection.

    Any printing counts. A non-existent collection returns an empty set.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT card_id FROM collection_cards WHERE collection_id = $1",
            collection_id,
        )
    return frozenset(r["card_id"] for r in rows)


async def build_ownership_map(
    pool: asyncpg.Pool,
    account_id: UUID | None,
    scryfall_ids: list[UUID],
) -> dict[UUID, list[CollectionMembership]]:
    """Map scryfall_id -> list of account collections containing that card.

    Deduplicates across multiple printings of the same oracle card in a collection.
    Returns an empty mapping when ``account_id`` is None or ``scryfall_ids`` is empty.
    """
    if account_id is None or not scryfall_ids:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH input_cards AS (
                SELECT scryfall_id, COALESCE(oracle_id, id) AS oracle_key
                FROM cards
                WHERE scryfall_id = ANY($2::uuid[])
            )
            SELECT ic.scryfall_id AS scryfall_id,
                   c.id AS collection_id,
                   c.name AS collection_name,
                   SUM(cc.quantity)::int AS quantity
            FROM input_cards ic
            JOIN cards owned_cards
              ON COALESCE(owned_cards.oracle_id, owned_cards.id) = ic.oracle_key
            JOIN collection_cards cc ON cc.card_id = owned_cards.id
            JOIN collections c ON c.id = cc.collection_id
            WHERE c.account_id = $1
            GROUP BY ic.scryfall_id, c.id, c.name
            """,
            account_id,
            scryfall_ids,
        )
    result: dict[UUID, list[CollectionMembership]] = {}
    for row in rows:
        result.setdefault(row["scryfall_id"], []).append(
            CollectionMembership(
                id=row["collection_id"],
                name=row["collection_name"],
                quantity=row["quantity"],
            )
        )
    return result


async def owned_quantities(
    pool: asyncpg.Pool,
    account_id: UUID | None,
    scryfall_ids: list[UUID],
) -> dict[UUID, int]:
    """Sum owned quantity per ``scryfall_id`` across all of the account's collections.

    Quantities are summed across every collection owned by ``account_id`` and
    every printing of the same oracle card. Returns an empty mapping when the
    account is anonymous or the input list is empty.
    """
    if account_id is None or not scryfall_ids:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH input_cards AS (
                SELECT scryfall_id, COALESCE(oracle_id, id) AS oracle_key
                FROM cards
                WHERE scryfall_id = ANY($2::uuid[])
            )
            SELECT input.scryfall_id,
                   SUM(cc.quantity)::int AS total
            FROM input_cards input
            JOIN cards owned
              ON COALESCE(owned.oracle_id, owned.id) = input.oracle_key
            JOIN collection_cards cc ON cc.card_id = owned.id
            JOIN collections c ON c.id = cc.collection_id
            WHERE c.account_id = $1
            GROUP BY input.scryfall_id
            """,
            account_id,
            scryfall_ids,
        )
    return {row["scryfall_id"]: row["total"] for row in rows}


async def get_owned_card_ids_for_collections(
    pool: asyncpg.Pool, collection_ids: list[UUID]
) -> frozenset[UUID]:
    """Return the distinct `cards.id` values owned across one or more collections.

    Returns an empty set when the input list is empty or when no collection rows exist.
    """
    if not collection_ids:
        return frozenset()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT canonical.id AS card_id
            FROM collection_cards cc
            JOIN cards owned ON owned.id = cc.card_id
            JOIN cards canonical
              ON COALESCE(canonical.oracle_id, canonical.id)
               = COALESCE(owned.oracle_id, owned.id)
             AND canonical.is_canonical
            WHERE cc.collection_id = ANY($1::uuid[])
            """,
            list(collection_ids),
        )
    return frozenset(row["card_id"] for row in rows)


async def _resolve_rows(
    pool: asyncpg.Pool, rows: list[ParsedCollectionRow]
) -> tuple[list[tuple[ParsedCollectionRow, UUID]], list[str]]:
    """Resolve parsed rows by exact Scryfall ID, then by card name.

    Returns:
        Tuple of (resolved pairs, unresolved names).
    """
    resolved: list[tuple[ParsedCollectionRow, UUID]] = []
    unresolved: list[str] = []
    for row in rows:
        card = None
        if row.scryfall_id is not None:
            card = await card_service.get_card_by_scryfall_id(pool, row.scryfall_id)
        if card is None:
            card = await card_service.resolve_card_by_name(pool, row.name)
        if card is None:
            unresolved.append(row.name)
            continue
        resolved.append((row, card.id))
    return resolved, unresolved


async def _merge_rows(
    conn: asyncpg.Connection,
    collection_id: UUID,
    resolved: list[tuple[ParsedCollectionRow, UUID]],
) -> tuple[int, int]:
    """Upsert resolved rows (increment quantity on conflict).

    Returns:
        Tuple of (imported_new, updated_existing).
    """
    imported = 0
    updated = 0
    for row, card_id in resolved:
        # xmax=0 on insert, nonzero on conflict-update — lets us count accurately.
        result = await conn.fetchval(
            """
            INSERT INTO collection_cards (
                collection_id, card_id, set_code, collector_number, foil,
                quantity, condition, language, tags, purchase_price, last_modified
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (collection_id, card_id, set_code, collector_number, foil)
            DO UPDATE SET
                quantity       = collection_cards.quantity + EXCLUDED.quantity,
                condition      = COALESCE(EXCLUDED.condition, collection_cards.condition),
                language       = COALESCE(EXCLUDED.language, collection_cards.language),
                tags           = EXCLUDED.tags,
                purchase_price = COALESCE(EXCLUDED.purchase_price, collection_cards.purchase_price),
                last_modified  = COALESCE(EXCLUDED.last_modified, collection_cards.last_modified)
            RETURNING (xmax = 0) AS inserted
            """,
            collection_id,
            card_id,
            row.set_code,
            row.collector_number,
            row.foil,
            row.quantity,
            row.condition,
            row.language,
            row.tags,
            row.purchase_price,
            row.last_modified,
        )
        if result:
            imported += 1
        else:
            updated += 1
    return imported, updated


async def _replace_rows(
    conn: asyncpg.Connection,
    collection_id: UUID,
    resolved: list[tuple[ParsedCollectionRow, UUID]],
) -> tuple[int, int]:
    """Delete all existing rows, then insert resolved rows.

    Returns:
        Tuple of (imported_new, removed_existing).
    """
    removed_raw = await conn.execute(
        "DELETE FROM collection_cards WHERE collection_id = $1", collection_id
    )
    removed = int(removed_raw.split(" ")[-1]) if removed_raw.startswith("DELETE ") else 0

    inserts = [
        (
            collection_id,
            card_id,
            row.set_code,
            row.collector_number,
            row.foil,
            row.quantity,
            row.condition,
            row.language,
            row.tags,
            row.purchase_price,
            row.last_modified,
        )
        for row, card_id in resolved
    ]
    if inserts:
        await conn.executemany(
            """
            INSERT INTO collection_cards (
                collection_id, card_id, set_code, collector_number, foil,
                quantity, condition, language, tags, purchase_price, last_modified
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (collection_id, card_id, set_code, collector_number, foil)
            DO UPDATE SET quantity = collection_cards.quantity + EXCLUDED.quantity
            """,
            inserts,
        )
    return len(resolved), removed


async def import_rows(
    pool: asyncpg.Pool,
    collection_id: UUID,
    rows: list[ParsedCollectionRow],
    mode: str,
    source: str = "csv",
) -> CollectionImportResponse:
    """Resolve parsed collection rows and persist them into a collection.

    Shared persistence pipeline for every collection import source (CSV text,
    Moxfield binder URLs). Resolution prefers exact Scryfall IDs and falls
    back to card-name matching.

    Modes:
        merge: upsert rows; existing printings have quantity added.
        replace: delete all rows in the collection, then insert parsed rows.

    Args:
        pool: asyncpg connection pool.
        collection_id: Target collection UUID.
        rows: Parsed rows from any import source.
        mode: 'merge' or 'replace'.
        source: Label used in log lines ('moxfield-csv', 'moxfield-url', ...).

    Returns:
        CollectionImportResponse with per-operation counts and unresolved names.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
    """
    resolved, unresolved = await _resolve_rows(pool, rows)

    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM collections WHERE id = $1", collection_id)
        if exists is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        async with conn.transaction():
            if mode == "replace":
                imported, removed = await _replace_rows(conn, collection_id, resolved)
                updated = 0
            else:
                imported, updated = await _merge_rows(conn, collection_id, resolved)
                removed = 0

    _log.info(
        "Imported %s rows into collection %s: imported=%d updated=%d removed=%d unresolved=%d",
        source,
        collection_id,
        imported,
        updated,
        removed,
        len(unresolved),
    )
    return CollectionImportResponse(
        imported=imported,
        updated=updated,
        removed=removed,
        unresolved=unresolved,
    )


async def import_csv(
    pool: asyncpg.Pool,
    collection_id: UUID,
    csv_text: str,
    mode: str,
    csv_format: str = "moxfield",
) -> CollectionImportResponse:
    """Import a supported CSV into a collection.

    Args:
        pool: asyncpg connection pool.
        collection_id: Target collection UUID.
        csv_text: Raw CSV text.
        mode: 'merge' or 'replace'.
        csv_format: Explicit source format ('moxfield' or 'manabox').

    Returns:
        CollectionImportResponse with per-operation counts and unresolved names.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
        ValueError: If the CSV is malformed or empty.
    """
    parsed = parse_collection_csv(csv_text, csv_format)
    return await import_rows(pool, collection_id, parsed, mode, source=f"{csv_format}-csv")


def _format_bool(value: bool) -> str:
    return "True" if value else "False"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def _format_decimal(value: Decimal | None) -> str:
    return "" if value is None else str(value)


async def export_csv(pool: asyncpg.Pool, collection_id: UUID) -> str:
    """Export a collection as a Moxfield-compatible CSV string.

    Raises:
        CollectionNotFoundError: If the collection does not exist.
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM collections WHERE id = $1", collection_id)
        if exists is None:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")
        rows = await conn.fetch(
            """
            SELECT cc.quantity, cc.set_code, cc.collector_number, cc.foil,
                   cc.condition, cc.language, cc.tags, cc.purchase_price, cc.last_modified,
                   c.name
            FROM collection_cards cc
            JOIN cards c ON cc.card_id = c.id
            WHERE cc.collection_id = $1
            ORDER BY c.name ASC, cc.set_code ASC, cc.collector_number ASC, cc.foil ASC
            """,
            collection_id,
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(_MOXFIELD_HEADERS)
    for row in rows:
        writer.writerow(
            [
                str(row["quantity"]),
                str(row["quantity"]),
                row["name"],
                row["set_code"],
                row["condition"] or "",
                row["language"] or "",
                "foil" if row["foil"] else "",
                ",".join(row["tags"] or []),
                _format_datetime(row["last_modified"]),
                row["collector_number"],
                "False",
                "False",
                _format_decimal(row["purchase_price"]),
            ]
        )
    return buffer.getvalue()

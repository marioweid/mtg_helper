"""Copy one explicitly approved account and public Scryfall sources into a local database.

Run with DATABASE_URL (the read-only source), LOCAL_NEW_CARDS_DATABASE_URL (an empty loopback
PostgreSQL database), and exactly one ADMIN_EMAILS value. The command never prints DSNs or rows.
"""

import asyncio
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import asyncpg

from mtg_helper.config import settings

_SCHEMA = Path(__file__).parents[1] / "src" / "mtg_helper" / "sql" / "schema.sql"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_PUBLIC_TABLES = (
    "recommendation_sources",
    "cards",
    "new_card_catalog",
    "new_card_catalog_state",
    "scryfall_tags",
    "scryfall_tag_memberships",
    "scryfall_tag_descendants",
    "scryfall_tag_state",
)


def _identity(dsn: str) -> tuple[str, int, str]:
    parts = urlsplit(dsn)
    host = unquote(parts.hostname or "").lower().rstrip(".")
    if host in _LOCAL_HOSTS:
        host = "loopback"
    return (host, parts.port or 5432, unquote(parts.path).lstrip("/"))


def validate_target(source_dsn: str, target_dsn: str) -> None:
    """Reject a source-equivalent, remote, or malformed local target before connecting."""
    source = _identity(source_dsn)
    target_parts = urlsplit(target_dsn)
    target = _identity(target_dsn)
    if target_parts.query or target_parts.fragment:
        raise ValueError("Local copy target must not contain query parameters or fragments.")
    if target[0] != "loopback":
        raise ValueError("Local copy target must use a loopback PostgreSQL host.")
    if not target[2]:
        raise ValueError("Local copy target must name a dedicated database.")
    if source == target:
        raise ValueError("Local copy target must not identify the source database.")


async def _require_empty_target(conn: asyncpg.Connection) -> None:
    exists = await conn.fetchval(
        "SELECT EXISTS ("
        "SELECT 1 FROM pg_namespace "
        "WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public') "
        "UNION ALL "
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' "
        "UNION ALL SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' "
        "UNION ALL SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'public'"
        ")"
    )
    if exists:
        raise ValueError("Local copy target is not empty; create a new dedicated database.")


async def _apply_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(_SCHEMA.read_text(encoding="utf-8"))


async def _copy_rows(
    source: asyncpg.Connection,
    target: asyncpg.Connection,
    table: str,
    query: str,
    *args: object,
) -> int:
    rows = await source.fetch(query, *args)
    if not rows:
        return 0
    columns = tuple(rows[0].keys())
    records = [dict(row) for row in rows]
    for record in records:
        if table == "decks":
            record["suggestion_collection_ids"] = []
        elif table == "deck_card_plans":
            record["collection_id"] = None
    placeholders = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    quoted = ", ".join(columns)
    await target.executemany(
        f"INSERT INTO {table} ({quoted}) VALUES ({placeholders})",  # noqa: S608
        [tuple(row[column] for column in columns) for row in records],
    )
    return len(rows)


async def copy_local(source_dsn: str, target_dsn: str, approved_email: str) -> dict[str, int]:
    """Perform a read-only, owner-filtered source export and verify target references."""
    validate_target(source_dsn, target_dsn)
    source = await asyncpg.connect(
        source_dsn, server_settings={"default_transaction_read_only": "on"}
    )
    target = None
    counts: dict[str, int] = {}
    try:
        async with source.transaction(isolation="repeatable_read", readonly=True):
            target = await asyncpg.connect(target_dsn)
            await _require_distinct_database(source, target)
            await _require_empty_target(target)
            await _apply_schema(target)
            await _require_matching_source_generations(source)
            owner = await source.fetchrow(
                "SELECT * FROM accounts WHERE lower(email) = lower($1)", approved_email
            )
            if owner is None:
                raise ValueError("Configured admin account was not found in the source database.")
            async with target.transaction():
                for table in _PUBLIC_TABLES:
                    counts[table] = await _copy_rows(
                        source, target, table, f"SELECT * FROM {table}"
                    )
                counts["accounts"] = await _copy_rows(
                    source, target, "accounts", "SELECT * FROM accounts WHERE id = $1", owner["id"]
                )
                counts["decks"] = await _copy_rows(
                    source,
                    target,
                    "decks",
                    "SELECT * FROM decks WHERE lower(owner_email) = lower($1)",
                    approved_email,
                )
                counts["deck_cards"] = await _copy_deck_rows(
                    source, target, "deck_cards", approved_email
                )
                counts["deck_card_plans"] = await _copy_deck_rows(
                    source, target, "deck_card_plans", approved_email
                )
                counts["new_card_dismissals"] = await _copy_dismissals(
                    source, target, owner["id"], approved_email
                )
                await _verify_target(target, owner["id"], approved_email)
        return counts
    finally:
        await source.close()
        if target is not None:
            await target.close()


async def _copy_deck_rows(
    source: asyncpg.Connection, target: asyncpg.Connection, table: str, email: str
) -> int:
    return await _copy_rows(
        source,
        target,
        table,
        f"SELECT child.* FROM {table} child JOIN decks d ON d.id = child.deck_id "  # noqa: S608
        "WHERE lower(d.owner_email) = lower($1)",
        email,
    )


async def _require_distinct_database(
    source: asyncpg.Connection, target: asyncpg.Connection
) -> None:
    query = (
        "SELECT current_database(), oid, pg_postmaster_start_time() "
        "FROM pg_database WHERE datname = current_database()"
    )
    # Compare the connected cluster, not DNS spelling or proxy routing, before any target write.
    if await source.fetchrow(query) == await target.fetchrow(query):
        raise ValueError("Local copy target must not identify the source database.")


async def _copy_dismissals(
    source: asyncpg.Connection, target: asyncpg.Connection, account_id: object, email: str
) -> int:
    return await _copy_rows(
        source,
        target,
        "new_card_dismissals",
        "SELECT dismissed.* FROM new_card_dismissals dismissed "
        "JOIN decks d ON d.id = dismissed.deck_id "
        "WHERE dismissed.account_id = $1 AND lower(d.owner_email) = lower($2)",
        account_id,
        email,
    )


async def _verify_target(target: asyncpg.Connection, owner_id: object, email: str) -> None:
    decks = await target.fetchval(
        "SELECT count(*) FROM decks WHERE lower(owner_email) = lower($1)", email
    )
    copied = await target.fetchval("SELECT count(*) FROM decks")
    if decks != copied:
        raise ValueError("Local copy owner verification failed.")
    account = await target.fetchval("SELECT id FROM accounts")
    if account != owner_id:
        raise ValueError("Local copy profile verification failed.")
    broken = await target.fetchval(
        "SELECT EXISTS (SELECT 1 FROM deck_cards dc "
        "LEFT JOIN decks d ON d.id = dc.deck_id LEFT JOIN cards c ON c.id = dc.card_id "
        "WHERE d.id IS NULL OR c.id IS NULL)"
    )
    if broken:
        raise ValueError("Local copy reference verification failed.")
    plans = await target.fetchval(
        "SELECT EXISTS (SELECT 1 FROM deck_card_plans p LEFT JOIN decks d ON d.id = p.deck_id "
        "LEFT JOIN cards c ON c.id = p.card_id LEFT JOIN collections cl ON cl.id = p.collection_id "
        "WHERE d.id IS NULL OR c.id IS NULL OR (p.collection_id IS NOT NULL AND cl.id IS NULL))"
    )
    collection_cards = await target.fetchval(
        "SELECT EXISTS (SELECT 1 FROM collection_cards cc "
        "LEFT JOIN collections cl ON cl.id = cc.collection_id "
        "LEFT JOIN cards c ON c.id = cc.card_id WHERE cl.id IS NULL OR c.id IS NULL)"
    )
    dismissals = await target.fetchval(
        "SELECT EXISTS (SELECT 1 FROM new_card_dismissals n LEFT JOIN decks d ON d.id = n.deck_id "
        "LEFT JOIN accounts a ON a.id = n.account_id WHERE d.id IS NULL OR a.id IS NULL)"
    )
    if plans or collection_cards or dismissals:
        raise ValueError("Local copy reference verification failed.")
    await _require_matching_source_generations(target)


async def _require_matching_source_generations(conn: asyncpg.Connection) -> None:
    matches = await conn.fetchval(
        "SELECT c.source_sha256 = t.source_sha256 FROM new_card_catalog_state c "
        "CROSS JOIN scryfall_tag_state t"
    )
    if matches is not True:
        raise ValueError("Scryfall card and tag sources must have matching generations.")


def _approved_admin() -> str:
    admins = [email.strip() for email in settings.admin_emails if email.strip()]
    if len(admins) != 1:
        raise ValueError("Local copy requires exactly one configured approved admin account.")
    return admins[0]


def main() -> None:
    """Run the narrowly authorized export and print aggregate counts only."""
    target_dsn = os.environ.get("LOCAL_NEW_CARDS_DATABASE_URL", "")
    if not target_dsn:
        raise ValueError("Set LOCAL_NEW_CARDS_DATABASE_URL to a new loopback database.")
    counts = asyncio.run(copy_local(settings.database_url, target_dsn, _approved_admin()))
    print(
        "Local New Cards copy complete:",
        ", ".join(f"{key}={value}" for key, value in counts.items()),
    )


if __name__ == "__main__":
    main()

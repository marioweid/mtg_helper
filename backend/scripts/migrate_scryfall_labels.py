"""Safely replace saved global-label selections with Scryfall source identities.

Run against an isolated backup first.  The command never reads the application
``DATABASE_URL`` and requires both ``--apply`` and a private report path before
it changes a database.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

import asyncpg


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def _is_safe_target(database_url: str) -> bool:
    """Require an explicitly named local or approved production target."""
    return database_url != os.environ.get("DATABASE_URL")


async def _load_source(conn: asyncpg.Connection) -> dict[str, set[UUID]]:
    state = await conn.fetchrow(
        "SELECT source_sha256 FROM scryfall_tag_state "
        "JOIN new_card_catalog_state USING (singleton) "
        "WHERE scryfall_tag_state.source_sha256 = new_card_catalog_state.source_sha256"
    )
    if state is None:
        raise ValueError("Scryfall card/tag generation is absent or mismatched; refusing cutover")
    rows = await conn.fetch("SELECT id, slug, metadata FROM scryfall_tags")
    if not rows:
        raise ValueError("Scryfall Oracle-tag catalog is empty; refusing cutover")
    aliases: dict[str, set[UUID]] = {}
    for row in rows:
        metadata = (
            json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
        )
        for value in [row["slug"], metadata.get("label"), *(metadata.get("aliases") or [])]:
            aliases.setdefault(value.strip().lower(), set()).add(row["id"])
    return aliases


async def _plan(conn: asyncpg.Connection, aliases: dict[str, set[UUID]]) -> tuple[dict, list[dict]]:
    rows = await conn.fetch(
        "SELECT id, archetype_tags FROM decks WHERE cardinality(archetype_tags) > 0"
    )
    updates: dict[str, list[str]] = {}
    unresolved: list[dict] = []
    for row in rows:
        selected: list[str] = []
        for intent in row["archetype_tags"]:
            matches = aliases.get(intent.strip().lower(), set())
            if len(matches) == 1:
                selected.append(str(next(iter(matches))))
            else:
                unresolved.append(
                    {"deck_id": str(row["id"]), "intent": intent, "matches": len(matches)}
                )
        updates[str(row["id"])] = selected
    return updates, unresolved


async def _apply(conn: asyncpg.Connection, updates: dict[str, list[str]]) -> None:
    for deck_id, tags in updates.items():
        await conn.execute(
            "UPDATE decks SET archetype_tags = $2 WHERE id = $1", UUID(deck_id), tags
        )
    await conn.execute("ALTER TABLE cards DROP COLUMN IF EXISTS tags")
    await conn.execute("ALTER TABLE cards DROP COLUMN IF EXISTS hub_tags")
    await conn.execute("ALTER TABLE cards DROP COLUMN IF EXISTS mtgjson_tags")
    await conn.execute("ALTER TABLE cards DROP COLUMN IF EXISTS traits")
    await conn.execute("ALTER TABLE cards DROP COLUMN IF EXISTS token_types")
    await conn.execute("DROP TABLE IF EXISTS mtgjson_card_metadata, mtgjson_keywords CASCADE")


async def main() -> None:
    """Print aggregate dry-run data or apply a reviewed cutover transaction."""
    args = _arguments()
    if not _is_safe_target(args.database_url):
        raise SystemExit("Refusing application DATABASE_URL; use an isolated rehearsal target")
    conn = await asyncpg.connect(args.database_url)
    try:
        aliases = await _load_source(conn)
        updates, unresolved = await _plan(conn, aliases)
        summary = {"decks": len(updates), "unresolved_intents": len(unresolved)}
        if not args.apply:
            print(json.dumps(summary, sort_keys=True))
            return
        if args.report is None:
            raise ValueError("--apply requires --report outside the repository")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"unresolved": unresolved}, indent=2), encoding="utf-8")
        async with conn.transaction():
            await _apply(conn, updates)
        print(json.dumps(summary, sort_keys=True))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

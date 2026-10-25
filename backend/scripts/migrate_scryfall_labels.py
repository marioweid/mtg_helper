"""Review and apply the one-time Scryfall source-identity cutover.

The command is deliberately limited to an isolated rehearsal database unless
an operator supplies the separately issued production approval token. Apply
never starts from the application's ``DATABASE_URL``.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import asyncpg

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--production-approval")
    return parser.parse_args()


def _is_safe_target(database_url: str, production_approval: str | None = None) -> bool:
    """Accept only an isolated rehearsal target or an explicit approval match."""
    if _target_identity(database_url) == _target_identity(os.environ.get("DATABASE_URL", "")):
        return False
    target = urlparse(database_url)
    database = target.path.removeprefix("/")
    if target.hostname in _LOCAL_HOSTS and database.endswith(("_test", "_rehearsal")):
        return True
    return production_approval == os.environ.get("CUTOVER_PRODUCTION_APPROVAL") and bool(
        production_approval
    )


def _target_identity(database_url: str) -> tuple[str, int, str, str] | None:
    """Normalize local DSNs so localhost aliases cannot bypass the app-target guard."""
    target = urlparse(database_url)
    if not target.hostname or not target.path:
        return None
    host = "loopback" if target.hostname in _LOCAL_HOSTS else target.hostname.lower()
    return host, target.port or 5432, target.path.removeprefix("/"), target.username or ""


def _private_report_path(report: Path) -> Path:
    """Validate that a report is private, new, and cannot enter the repository."""
    resolved = report.expanduser().resolve()
    if resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("--report must be outside the repository")
    if resolved.exists():
        raise ValueError("--report must be a new path; refusing to overwrite private intent")
    return resolved


async def _load_source(conn: asyncpg.Connection) -> tuple[dict[str, set[UUID]], set[UUID]]:
    state = await conn.fetchrow(
        "SELECT t.source_sha256 FROM scryfall_tag_state AS t "
        "JOIN new_card_catalog_state AS c ON c.singleton = t.singleton "
        "WHERE t.source_sha256 = c.source_sha256"
    )
    if state is None:
        raise ValueError("Scryfall card/tag generation is absent or mismatched; refusing cutover")
    rows = await conn.fetch("SELECT id, slug, metadata FROM scryfall_tags")
    if not rows:
        raise ValueError("Scryfall Oracle-tag catalog is empty; refusing cutover")
    aliases: dict[str, set[UUID]] = {}
    identities: set[UUID] = set()
    for row in rows:
        identities.add(row["id"])
        metadata = (
            json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
        )
        for value in [row["slug"], metadata.get("label"), *(metadata.get("aliases") or [])]:
            if isinstance(value, str) and value.strip():
                aliases.setdefault(value.strip().lower(), set()).add(row["id"])
    return aliases, identities


def _source_identity(
    intent: str, aliases: dict[str, set[UUID]], identities: set[UUID]
) -> UUID | None:
    """Return one source identity without remapping an already converted selection."""
    try:
        parsed = UUID(intent)
    except ValueError:
        matches = aliases.get(intent.strip().lower(), set())
        return next(iter(matches)) if len(matches) == 1 else None
    return parsed if parsed in identities else None


async def _plan(
    conn: asyncpg.Connection, aliases: dict[str, set[UUID]], identities: set[UUID]
) -> tuple[dict[UUID, list[str]], list[dict[str, str]]]:
    rows = await conn.fetch(
        "SELECT id, archetype_tags FROM decks WHERE cardinality(archetype_tags) > 0"
    )
    updates: dict[UUID, list[str]] = {}
    unresolved: list[dict[str, str]] = []
    for row in rows:
        selected: list[str] = []
        for intent in row["archetype_tags"]:
            source_id = _source_identity(intent, aliases, identities)
            if source_id is None:
                unresolved.append({"deck_id": str(row["id"]), "intent": intent})
            elif str(source_id) not in selected:
                selected.append(str(source_id))
        if selected != list(row["archetype_tags"]):
            updates[row["id"]] = selected
    return updates, unresolved


def _write_report(report: Path, unresolved: list[dict[str, str]]) -> None:
    """Create a private report atomically before destructive work can begin."""
    report.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"unresolved": unresolved}, handle, indent=2)
        handle.write("\n")
    os.chmod(report, 0o600)


async def _apply(conn: asyncpg.Connection, updates: dict[UUID, list[str]]) -> None:
    """Apply source selections and remove retired global-label storage atomically."""
    for deck_id, tags in updates.items():
        await conn.execute("UPDATE decks SET archetype_tags = $2 WHERE id = $1", deck_id, tags)
    await conn.execute(_LEGACY_DROP_SQL)


_LEGACY_DROP_SQL = """
DROP VIEW IF EXISTS deck_detail_view;
DROP TABLE IF EXISTS theme_group_suggestions CASCADE;
DROP TABLE IF EXISTS theme_group_members CASCADE;
DROP TABLE IF EXISTS theme_groups CASCADE;
DROP TABLE IF EXISTS archidekt_tag_card_stats CASCADE;
DROP TABLE IF EXISTS archidekt_tags CASCADE;
DROP TABLE IF EXISTS moxfield_hub_card_stats CASCADE;
DROP TABLE IF EXISTS moxfield_hubs CASCADE;
DROP TABLE IF EXISTS mtgjson_keywords CASCADE;
DROP TABLE IF EXISTS mtgjson_card_metadata CASCADE;
DROP INDEX IF EXISTS idx_cards_tags;
DROP INDEX IF EXISTS idx_cards_all_tags_gin;
DROP INDEX IF EXISTS idx_cards_traits;
DROP INDEX IF EXISTS idx_cards_hub_tags;
DROP INDEX IF EXISTS idx_cards_mtgjson_tags;
ALTER TABLE cards DROP COLUMN IF EXISTS tags;
ALTER TABLE cards DROP COLUMN IF EXISTS hub_tags;
ALTER TABLE cards DROP COLUMN IF EXISTS mtgjson_tags;
ALTER TABLE cards DROP COLUMN IF EXISTS traits;
ALTER TABLE cards DROP COLUMN IF EXISTS token_types;
CREATE VIEW deck_detail_view AS
SELECT
    dc.deck_id, dc.id AS deck_card_id, dc.quantity, dc.categories, dc.added_by, dc.ai_reasoning,
    c.id AS card_id, c.scryfall_id, c.oracle_id, c.name, c.mana_cost, c.cmc, c.type_line,
    c.oracle_text, c.color_identity, c.image_uri, c.rarity, c.keywords,
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'id', t.id, 'slug', t.slug, 'label', t.metadata->>'label'
        ) ORDER BY t.slug)
        FROM scryfall_tag_memberships m
        JOIN scryfall_tags t ON t.id = m.tag_id
        WHERE m.oracle_id = c.oracle_id
    ), '[]'::jsonb) AS oracle_tags,
    CASE WHEN (c.prices->>'eur') IS NULL THEN NULL
         ELSE ROUND((c.prices->>'eur')::numeric * 100)::integer END AS price_eur_cents,
    c.power, c.game_changer
FROM deck_cards dc JOIN cards c ON dc.card_id = c.id;
"""


async def main() -> None:
    """Print a safe aggregate plan or atomically apply reviewed source identities."""
    args = _arguments()
    if not _is_safe_target(args.database_url, args.production_approval):
        raise SystemExit(
            "Refusing unsafe target; use an isolated rehearsal target or production approval"
        )
    report = _private_report_path(args.report) if args.apply and args.report else None
    if args.apply and report is None:
        raise SystemExit("--apply requires a new private --report outside the repository")
    conn = await asyncpg.connect(args.database_url)
    try:
        async with conn.transaction():
            aliases, identities = await _load_source(conn)
            updates, unresolved = await _plan(conn, aliases, identities)
            summary = {"decks": len(updates), "unresolved_intents": len(unresolved)}
            if not args.apply:
                print(json.dumps(summary, sort_keys=True))
                return
            _write_report(report, unresolved)
            await _apply(conn, updates)
        print(json.dumps(summary, sort_keys=True))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

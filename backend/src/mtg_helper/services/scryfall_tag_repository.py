"""Atomic Oracle-tag publications bound to the same Scryfall card generation."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from mtg_helper.services.recommendations.snapshots import pack, unpack
from mtg_helper.services.scryfall_exports import BulkExport
from mtg_helper.services.scryfall_tags import OracleTagCatalog, parse_tags


@dataclass(kw_only=True)
class TagPublication:
    """Verified source metadata/memberships and their immutable, card-bound snapshot."""

    catalog: OracleTagCatalog
    blob: bytes
    digest: str
    cards_hash: str
    archive_hash: str
    manifest: dict

    @property
    def membership_count(self) -> int:
        return sum(len(tag.taggings) for tag in self.catalog.tags.values())


def prepare(
    content: bytes,
    cards_hash: str,
    oracle_ids: set[UUID],
    *,
    card_export: BulkExport,
    tag_export: BulkExport,
) -> TagPublication:
    """Validate all source identities before any card/tag writes, then freeze provenance.

    Args:
        content: The compressed Oracle-tag export.
        cards_hash: Immutable normalized card-source digest from the same sync.
        oracle_ids: All source identities, including non-Commander cards.
        card_export: Manifest receipt for Oracle card facts.
        tag_export: Manifest receipt for Oracle tags.

    Returns:
        A ready-to-publish generation; direct weights and annotations are preserved.

    Raises:
        ValueError: If source identities or receipt kinds do not agree.
    """
    if card_export.type != "oracle_cards" or tag_export.type != "oracle_tags":
        raise ValueError("Wrong Scryfall export receipt kinds; retain last-good tags")
    catalog = parse_tags(content)
    tagged = {membership.oracle_id for tag in catalog.tags.values() for membership in tag.taggings}
    unknown = tagged - oracle_ids
    if unknown:
        raise ValueError(
            f"Scryfall tags reference {len(unknown)} absent Oracle identities; retry complete sync"
        )
    archive_hash = hashlib.sha256(content).hexdigest()
    manifest = {
        "oracle_cards": card_export.model_dump(mode="json"),
        "oracle_tags": tag_export.model_dump(mode="json"),
    }
    blob, digest = pack(
        {
            "cards_sha256": cards_hash,
            "archive_sha256": archive_hash,
            "manifest": manifest,
            "tags": catalog.records(),
        }
    )
    return TagPublication(
        catalog=catalog,
        blob=blob,
        digest=digest,
        cards_hash=cards_hash,
        archive_hash=archive_hash,
        manifest=manifest,
    )


async def validate_generation(conn: asyncpg.Connection, prepared: TagPublication) -> None:
    """Refuse empty/truncated tags or memberships while retaining the last-good generation."""
    previous = await conn.fetchrow("SELECT tag_count, membership_count FROM scryfall_tag_state")
    counts = {
        "tag_count": len(prepared.catalog.tags),
        "membership_count": prepared.membership_count,
    }
    for field, count in counts.items():
        minimum = max(1000, int(previous[field] * 0.9)) if previous else 1000
        if count < minimum:
            raise ValueError(f"Scryfall {field} shrank unexpectedly; retain last-good tags")


async def publish(
    conn: asyncpg.Connection,
    prepared: TagPublication,
    started: datetime,
) -> None:
    """Publish after card facts inside the existing locked Scryfall transaction.

    Args:
        conn: Connection holding the catalog advisory lock and enclosing transaction.
        prepared: Fully validated generation, bound to the published card source.
        started: Sync start time used by the shared generation lock.

    Raises:
        ValueError: If the matching complete card generation has not been published.
    """
    if not conn.is_in_transaction():
        raise ValueError("Scryfall tag publication requires the enclosing card transaction")
    await validate_generation(conn, prepared)
    current = await conn.fetchrow("SELECT source_sha256, started_at FROM new_card_catalog_state")
    if current is None or current["source_sha256"] != prepared.cards_hash:
        raise ValueError("Scryfall card/tag generation mismatch; retain last-good sources")
    if current["started_at"] != started:
        raise ValueError("Scryfall card/tag generation mismatch; retain last-good sources")
    await conn.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) "
        "VALUES ($1, 'oracle_tags', $2) ON CONFLICT DO NOTHING",
        prepared.digest,
        prepared.blob,
    )
    # DELETE is MVCC-safe; TRUNCATE could expose an empty catalog to an older reader snapshot.
    await conn.execute("DELETE FROM scryfall_tag_memberships")
    await conn.execute("DELETE FROM scryfall_tag_descendants")
    await conn.execute("DELETE FROM scryfall_tags")
    await conn.copy_records_to_table(
        "scryfall_tags",
        columns=["id", "slug", "metadata"],
        records=[
            (
                tag.id,
                tag.slug,
                json.dumps(tag.model_dump(mode="json", exclude={"taggings"}, exclude_unset=True)),
            )
            for tag in prepared.catalog.tags.values()
        ],
    )
    await conn.copy_records_to_table(
        "scryfall_tag_memberships",
        columns=["tag_id", "oracle_id", "details"],
        records=[
            (tag.id, membership.oracle_id, membership.model_dump_json(exclude_unset=True))
            for tag in prepared.catalog.tags.values()
            for membership in tag.taggings
        ],
    )
    await conn.copy_records_to_table(
        "scryfall_tag_descendants",
        columns=["ancestor_id", "descendant_id"],
        records=[
            (ancestor, descendant)
            for ancestor, descendants in prepared.catalog.descendants.items()
            for descendant in descendants
        ],
    )
    await conn.execute(
        "INSERT INTO scryfall_tag_state "
        "(singleton, source_sha256, tag_sha256, archive_sha256, manifest, started_at, "
        "published_at, tag_count, membership_count) "
        "VALUES (true, $1, $2, $3, $4::jsonb, $5, now(), $6, $7) "
        "ON CONFLICT (singleton) DO UPDATE SET source_sha256 = EXCLUDED.source_sha256, "
        "tag_sha256 = EXCLUDED.tag_sha256, archive_sha256 = EXCLUDED.archive_sha256, "
        "manifest = EXCLUDED.manifest, started_at = EXCLUDED.started_at, "
        "published_at = EXCLUDED.published_at, tag_count = EXCLUDED.tag_count, "
        "membership_count = EXCLUDED.membership_count",
        prepared.cards_hash,
        prepared.digest,
        prepared.archive_hash,
        json.dumps(prepared.manifest),
        started,
        len(prepared.catalog.tags),
        prepared.membership_count,
    )


async def publication_status(pool: asyncpg.Pool) -> dict:
    """Expose publication/receipt times and card binding, never disguise an absent catalog."""
    row = await pool.fetchrow(
        "SELECT t.*, c.source_sha256 AS current_source_sha256 "
        "FROM scryfall_tag_state t LEFT JOIN new_card_catalog_state c ON c.singleton = t.singleton"
    )
    if row is None:
        return {"status": "unavailable"}
    return {
        "status": "current"
        if row["source_sha256"] == row["current_source_sha256"]
        else "mismatched",
        "card_source_sha256": row["source_sha256"],
        "tag_source_sha256": row["tag_sha256"],
        "archive_sha256": row["archive_sha256"],
        "manifest": json.loads(row["manifest"]),
        "started_at": row["started_at"].isoformat(),
        "published_at": row["published_at"].isoformat(),
        "tag_count": row["tag_count"],
        "membership_count": row["membership_count"],
    }


def restore(blob: bytes, digest: str, cards_hash: str) -> OracleTagCatalog:
    """Verify an immutable tag snapshot and its card binding before replaying searches."""
    snapshot = unpack(blob, digest)
    if snapshot["cards_sha256"] != cards_hash:
        raise ValueError("Scryfall card/tag snapshot mismatch; restore matching sources")
    return OracleTagCatalog.from_records(snapshot["tags"])

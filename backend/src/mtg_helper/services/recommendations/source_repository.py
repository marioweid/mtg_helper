"""Atomic catalog snapshots and bounded generation caching shared by app workers."""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

import asyncpg

from mtg_helper.services.recommendations.snapshots import (
    Sources,
    normalize_cards,
    pack,
    packaged_rules,
    unpack,
)
from mtg_helper.services.recommendations.source import Card

_log = logging.getLogger(__name__)


@dataclass(kw_only=True)
class Publication:
    cards: dict[str, Card]
    blob: bytes
    digest: str


def prepare(cards: list[Card]) -> Publication:
    normalized = normalize_cards(cards)
    blob, digest = pack(normalized)
    return Publication(cards={c["oracle_id"]: c for c in normalized}, blob=blob, digest=digest)


@lru_cache(maxsize=1)
def rules_resource() -> tuple[bytes, str]:
    return packaged_rules()


async def publish(conn: asyncpg.Connection, prepared: Publication) -> None:
    await conn.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'cards', $2) "
        "ON CONFLICT DO NOTHING",
        prepared.digest,
        prepared.blob,
    )
    try:
        blob, digest = await asyncio.to_thread(rules_resource)
    except (OSError, ValueError) as exc:
        # A broken optional pilot resource must not block the legacy card sync.
        _log.error(
            "Discover rules unavailable (%s); restore the pinned packaged resource",
            type(exc).__name__,
        )
        return
    await conn.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload) VALUES ($1, 'rules', $2) "
        "ON CONFLICT DO NOTHING",
        digest,
        blob,
    )


def decode_sources(cards_blob: bytes, rules_blob: bytes, key: tuple[str, str]) -> Sources:
    return Sources.load(
        cards=unpack(cards_blob, key[0]),
        rules=unpack(rules_blob, key[1]),
        card_hash=key[0],
        rules_hash=key[1],
    )


class SourceRepository:
    """Cache at most two verified generations; PostgreSQL is the durable source of truth."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.cache: OrderedDict[tuple[str, str], Sources] = OrderedDict()
        self.lock = asyncio.Lock()

    async def load(self, cards_hash: str, rules_hash: str) -> Sources:
        key = (cards_hash, rules_hash)
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            rows = await self.pool.fetch(
                "SELECT sha256, kind, payload FROM recommendation_sources "
                "WHERE sha256 = ANY($1::text[])",
                list(key),
            )
            by_hash = {row["sha256"]: row for row in rows}
            if (
                cards_hash not in by_hash
                or rules_hash not in by_hash
                or by_hash[cards_hash]["kind"] != "cards"
                or by_hash[rules_hash]["kind"] != "rules"
            ):
                raise ValueError("Source snapshot unavailable; ask an admin to sync cards")
            sources = await asyncio.to_thread(
                decode_sources,
                by_hash[cards_hash]["payload"],
                by_hash[rules_hash]["payload"],
                key,
            )
            self.cache[key] = sources
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
            return sources

    async def current(self) -> tuple[str, str]:
        row = await self.pool.fetchrow("SELECT source_sha256 FROM new_card_catalog_state")
        if row is None or row["source_sha256"] is None:
            raise ValueError("Complete source catalog unavailable; run Admin card sync")
        _, rules_hash = await asyncio.to_thread(rules_resource)
        return row["source_sha256"], rules_hash


async def prune(pool: asyncpg.Pool) -> int:
    """Explicit maintenance only; never prune active, held, latest or recent run generations."""
    result = await pool.execute(
        "DELETE FROM recommendation_sources s WHERE s.published_at < now() - interval '30 days' "
        "AND s.kind = 'cards' AND s.sha256 <> COALESCE("
        "(SELECT source_sha256 FROM new_card_catalog_state), '') "
        "AND NOT EXISTS (SELECT 1 FROM recommendation_runs r "
        "WHERE r.source_hash = s.sha256 OR r.rules_hash = s.sha256)"
    )
    return int(result.split()[-1])

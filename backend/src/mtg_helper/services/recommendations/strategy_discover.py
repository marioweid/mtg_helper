# ruff: noqa: E501 -- parameterized SQL retains its readable relational shape.
"""Local, deterministic Scryfall strategy matching for Discover.

The module owns saved intent, source consistency, exclusions, and cursor validation.
It deliberately has no provider dependency: model assistance is an explicit, separate
legacy accounting action and never participates in browsing.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.models.recommendations import (
    DiscoverMatches,
    DiscoverSourceStatus,
    DiscoverStrategy,
    DiscoverStrategySave,
    DiscoverTerms,
    StrategyMatch,
    StrategyMatchEvidence,
)
from mtg_helper.services.recommendations.artwork import safe_uri
from mtg_helper.services.recommendations.planning import Planner
from mtg_helper.services.recommendations.repository import DiscoveryError, Owner, owned_deck
from mtg_helper.services.recommendations.search_sql import MATCH_SQL
from mtg_helper.services.recommendations.term_queries import StrategyQuery, selected_terms

_SOURCE_MAX_AGE = timedelta(days=2)
_PAGE_SIZE = 40


def _json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def _cursor(value: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def _decode_cursor(value: str) -> dict[str, object]:
    try:
        decoded = base64.urlsafe_b64decode(value.encode()).decode()
        data = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("Invalid Discover continuation; restart browsing", 409) from exc
    if not isinstance(data, dict):
        raise DiscoveryError("Invalid Discover continuation; restart browsing", 409)
    return data


def _strategy(row: asyncpg.Record | None, *, needs_review: bool = False) -> DiscoverStrategy | None:
    if row is None:
        return None
    return DiscoverStrategy(
        prose=row["prose"],
        queries=_queries(row),
        revision=row["revision"],
        updated_at=row["updated_at"],
        needs_review=needs_review,
    )


def _queries(row: asyncpg.Record) -> list[StrategyQuery]:
    raw = _json(row["queries"])
    if not isinstance(raw, list):
        raise DiscoveryError("Saved Discover searches are invalid; review the strategy", 409)
    return [StrategyQuery.model_validate(query) for query in raw]


async def source_status(conn: asyncpg.Connection) -> DiscoverSourceStatus:
    """Describe the local card/tag publication without refreshing or modifying it."""
    cards = await conn.fetchrow("SELECT * FROM new_card_catalog_state WHERE singleton")
    tags = await conn.fetchrow("SELECT * FROM scryfall_tag_state WHERE singleton")
    if cards is None or tags is None:
        return DiscoverSourceStatus(
            status="unavailable", warning="Scryfall card or tag sources are unavailable."
        )
    if cards["source_sha256"] != tags["source_sha256"]:
        return DiscoverSourceStatus(
            status="mismatched",
            card_updated_at=cards["published_at"],
            tag_updated_at=tags["published_at"],
            warning="Scryfall card and tag sources are from different generations.",
        )
    stale = datetime.now(UTC) - min(cards["published_at"], tags["published_at"]) > _SOURCE_MAX_AGE
    return DiscoverSourceStatus(
        status="stale" if stale else "ready",
        card_updated_at=cards["published_at"],
        tag_updated_at=tags["published_at"],
        warning="Showing last-known Scryfall legality; sources are over two days old."
        if stale
        else None,
    )


async def source_terms(conn: asyncpg.Connection, *, prose: str = "") -> DiscoverTerms:
    """Read all picker terms, or a bounded source-relevant catalog for explicit AI setup."""
    source = await source_status(conn)
    if source.status in {"unavailable", "mismatched"}:
        raise DiscoveryError(source.warning or "Scryfall sources unavailable", 503)
    tags = await conn.fetch(
        "SELECT id, slug, COALESCE(metadata->>'label',slug) AS label FROM scryfall_tags "
        "ORDER BY similarity(lower(COALESCE(metadata->>'label',slug) || ' ' || "
        "COALESCE(metadata->>'description','') || ' ' || COALESCE(metadata->>'aliases','')), "
        "lower($1)) DESC, lower(COALESCE(metadata->>'label',slug)), id "
        "LIMIT CASE WHEN $1='' THEN NULL ELSE 80 END",
        prose,
    )
    keywords = await conn.fetch(
        "SELECT keyword FROM (SELECT DISTINCT keyword FROM new_card_catalog n "
        "JOIN new_card_catalog_state s ON s.generation=n.generation "
        "CROSS JOIN LATERAL jsonb_array_elements_text("
        "COALESCE(n.source_facts->'keywords','[]'::jsonb)) keyword) source_keywords "
        "ORDER BY similarity(lower(keyword),lower($1)) DESC, lower(keyword), keyword "
        "LIMIT CASE WHEN $1='' THEN NULL ELSE 80 END",
        prose,
    )
    return DiscoverTerms(
        oracle_tags=[dict(row) for row in tags],
        printed_keywords=[row["keyword"] for row in keywords],
    )


class StrategyDiscover:
    """Expose a small owner-scoped interface for local Discover setup and matches."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def status(self, owner: Owner, deck_id: UUID) -> DiscoverMatches:
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                await owned_deck(conn, owner, deck_id)
                source = await source_status(conn)
                saved = await self._saved(conn, owner, deck_id)
                needs_review = saved is not None and not await self._terms_present(conn, saved)
                return DiscoverMatches(
                    status=self._status(source, saved),
                    source=source,
                    strategy=_strategy(saved, needs_review=needs_review),
                )

    async def terms(self, owner: Owner, deck_id: UUID) -> DiscoverTerms:
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                await owned_deck(conn, owner, deck_id)
                return await source_terms(conn)

    async def save(
        self, owner: Owner, deck_id: UUID, command: DiscoverStrategySave
    ) -> DiscoverStrategy:
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            await self._validate_terms(conn, *selected_terms(command.queries))
            existing = await self._saved(conn, owner, deck_id, lock=True)
            if existing and command.revision != existing["revision"]:
                raise DiscoveryError(
                    "Discover strategy changed elsewhere; reload before saving", 409
                )
            revision = uuid4()
            row = await conn.fetchrow(
                "INSERT INTO discover_strategies "
                "(deck_id, account_id, prose, queries, revision) "
                "VALUES ($1,$2,$3,$4::jsonb,$5) "
                "ON CONFLICT (deck_id) DO UPDATE SET account_id = EXCLUDED.account_id, "
                "prose = EXCLUDED.prose, queries = EXCLUDED.queries, revision = EXCLUDED.revision, "
                "updated_at = now() RETURNING *",
                deck_id,
                owner.account_id,
                command.prose,
                json.dumps([query.model_dump(mode="json") for query in command.queries]),
                revision,
            )
            saved = _strategy(row)
            if saved is None:
                raise RuntimeError("Discover strategy save did not return a row")
            return saved

    async def matches(
        self, owner: Owner, deck_id: UUID, cursor: str | None = None
    ) -> DiscoverMatches:
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                deck = await owned_deck(conn, owner, deck_id)
                source = await source_status(conn)
                saved = await self._saved(conn, owner, deck_id)
                status = self._status(source, saved)
                if status != "ready" and status != "stale":
                    return DiscoverMatches(status=status, source=source, strategy=_strategy(saved))
                assert saved is not None
                if not await self._terms_present(conn, saved):
                    return DiscoverMatches(
                        status="setup_needed",
                        source=source,
                        strategy=_strategy(saved, needs_review=True),
                    )
                state = await self._state_key(conn, deck, owner, saved, source=source)
                after = None
                if cursor:
                    token = _decode_cursor(cursor)
                    if token.get("state") != state:
                        raise DiscoveryError("Discover results changed; restart browsing", 409)
                    after = (
                        token.get("missing"),
                        token.get("rank"),
                        token.get("name"),
                        token.get("oracle_id"),
                    )
                    if (
                        type(after[0]) is not bool
                        or type(after[1]) is not int
                        or not all(isinstance(part, str) for part in after[2:])
                    ):
                        raise DiscoveryError("Invalid Discover continuation; restart browsing", 409)
                rows, total = await self._match_rows(conn, deck, owner, saved, after=after)
                cards = [self._match(row) for row in rows[:_PAGE_SIZE]]
                next_cursor = None
                if len(rows) > _PAGE_SIZE:
                    last = rows[_PAGE_SIZE - 1]
                    next_cursor = _cursor(
                        {
                            "state": state,
                            "missing": last["rank_missing"],
                            "rank": last["sort_rank"],
                            "name": last["sort_name"],
                            "oracle_id": str(last["oracle_id"]),
                        }
                    )
                return DiscoverMatches(
                    status=status,
                    source=source,
                    strategy=_strategy(saved),
                    cards=cards,
                    next_cursor=next_cursor,
                    total=total,
                )

    async def dismiss(self, owner: Owner, deck_id: UUID, oracle_id: UUID, *, undo: bool) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            if undo:
                await conn.execute(
                    "DELETE FROM discover_dismissals WHERE deck_id=$1 AND account_id=$2 AND oracle_id=$3",
                    deck_id,
                    owner.account_id,
                    oracle_id,
                )
                return
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM new_card_catalog WHERE oracle_id=$1)", oracle_id
            )
            if not exists:
                raise DiscoveryError("Discover card not found", 404)
            await conn.execute(
                "INSERT INTO discover_dismissals (deck_id, account_id, oracle_id) VALUES ($1,$2,$3) "
                "ON CONFLICT DO NOTHING",
                deck_id,
                owner.account_id,
                oracle_id,
            )

    async def plan(self, owner: Owner, deck_id: UUID, oracle_id: UUID) -> None:
        """Validate the current strategy and source before atomically planning one addition."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
            await conn.execute("SELECT pg_advisory_xact_lock_shared(71382041)")
            existing = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM deck_card_plans p JOIN cards c ON c.id=p.card_id "
                "WHERE p.deck_id=$1 AND p.direction='addition' AND c.oracle_id=$2)",
                deck_id,
                oracle_id,
            )
            if existing:
                return
            source = await source_status(conn)
            strategy = await self._saved(conn, owner, deck_id)
            if source.status not in {"ready", "stale"} or strategy is None:
                raise DiscoveryError("Strategy match is no longer current; refresh Discover", 409)
            if not await self._terms_present(conn, strategy):
                raise DiscoveryError("Review the saved Scryfall criteria before planning", 409)
            rows, _ = await self._match_rows(
                conn, deck, owner, strategy, oracle_id=oracle_id, limit=1
            )
            if not rows:
                raise DiscoveryError("Strategy match is no longer current; refresh Discover", 409)
            await Planner(self.pool).plan_in_transaction(conn, deck_id, oracle_id, owner=owner)

    async def _saved(
        self, conn: asyncpg.Connection, owner: Owner, deck_id: UUID, *, lock: bool = False
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            "SELECT * FROM discover_strategies WHERE deck_id=$1 AND account_id=$2"
            + (" FOR UPDATE" if lock else ""),
            deck_id,
            owner.account_id,
        )

    @staticmethod
    def _status(
        source: DiscoverSourceStatus, saved: asyncpg.Record | None
    ) -> Literal["ready", "stale", "setup_needed", "unavailable", "mismatched"]:
        if source.status in {"unavailable", "mismatched"}:
            return source.status
        if saved is None:
            return "setup_needed"
        return source.status

    async def _validate_terms(
        self, conn: asyncpg.Connection, tag_ids: list[UUID], keywords: list[str]
    ) -> None:
        if tag_ids:
            rows = await conn.fetch(
                "SELECT id FROM scryfall_tags WHERE id = ANY($1::uuid[])", tag_ids
            )
            found = {row["id"] for row in rows}
            if set(tag_ids) != found:
                raise DiscoveryError("One or more Oracle-Tag UUIDs are no longer available", 422)
        if keywords:
            rows = await conn.fetch(
                "SELECT DISTINCT keyword FROM new_card_catalog n "
                "JOIN new_card_catalog_state s ON s.generation=n.generation "
                "CROSS JOIN LATERAL jsonb_array_elements_text("
                "COALESCE(n.source_facts->'keywords','[]'::jsonb)) keyword "
                "WHERE keyword = ANY($1::text[])",
                keywords,
            )
            available = {row["keyword"] for row in rows}
            if set(keywords) != available:
                raise DiscoveryError(
                    "One or more printed keywords are not in the Scryfall catalog", 422
                )

    async def _terms_present(self, conn: asyncpg.Connection, strategy: asyncpg.Record) -> bool:
        """Detect retired source labels without changing prose or substituting a source term."""
        try:
            queries = _queries(strategy)
            await self._validate_terms(conn, *selected_terms(queries))
        except DiscoveryError:
            return False
        return bool(queries)

    async def _state_key(
        self,
        conn: asyncpg.Connection,
        deck: asyncpg.Record,
        owner: Owner,
        strategy: asyncpg.Record,
        *,
        source: DiscoverSourceStatus,
    ) -> str:
        exclusions = await conn.fetch(
            "SELECT c.oracle_id::text AS oracle_id FROM cards c JOIN deck_cards dc ON dc.card_id=c.id "
            "WHERE dc.deck_id=$1 UNION SELECT c.oracle_id::text FROM cards c "
            "JOIN deck_card_plans p ON p.card_id=c.id WHERE p.deck_id=$1 AND p.direction='addition' "
            "UNION SELECT oracle_id::text FROM discover_dismissals WHERE deck_id=$1 AND account_id=$2",
            deck["id"],
            owner.account_id,
        )
        state = {
            "ordering": "filtered-popularity-v1",
            "ranking": await conn.fetchval(
                "SELECT md5(COALESCE(string_agg(oracle_id::text || ':' || COALESCE(edhrec_rank::text,''), "
                "',' ORDER BY oracle_id::text),'')) FROM cards WHERE is_canonical"
            ),
            "revision": str(strategy["revision"]),
            "cards": source.card_updated_at.isoformat() if source.card_updated_at else "",
            "tags": source.tag_updated_at.isoformat() if source.tag_updated_at else "",
            "excluded": sorted(row["oracle_id"] for row in exclusions if row["oracle_id"]),
            "commanders": [str(deck["commander_id"]), str(deck["partner_id"])],
            "publication": await conn.fetchval(
                "SELECT c.generation::text || ':' || t.tag_sha256 FROM new_card_catalog_state c "
                "CROSS JOIN scryfall_tag_state t WHERE c.singleton AND t.singleton"
            ),
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    async def _match_rows(
        self,
        conn: asyncpg.Connection,
        deck: asyncpg.Record,
        owner: Owner,
        strategy: asyncpg.Record,
        *,
        after: tuple[object, object, object, object] | None = None,
        limit: int = 41,
        oracle_id: UUID | None = None,
    ) -> tuple[list[asyncpg.Record], int]:
        color_identity, commander_oracles = await self._commander_context(conn, deck)
        arguments = (
            strategy["queries"],
            color_identity,
            commander_oracles,
            deck["id"],
            owner.account_id,
            after[0] if after else None,
            after[1] if after else None,
            after[2] if after else None,
            after[3] if after else None,
            limit,
            oracle_id,
        )
        rows = await conn.fetch(MATCH_SQL, *arguments)
        return [row for row in rows if row["oracle_id"] is not None], rows[0]["total"]

    async def _commander_context(
        self, conn: asyncpg.Connection, deck: asyncpg.Record
    ) -> tuple[list[str], list[UUID]]:
        commanders = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
        colors = await conn.fetch(
            "SELECT n.source_facts->'color_identity' AS colors FROM cards c "
            "JOIN new_card_catalog n ON n.oracle_id=c.oracle_id "
            "JOIN new_card_catalog_state s ON s.generation=n.generation "
            "WHERE c.id = ANY($1::uuid[])",
            commanders,
        )
        if len(colors) != len(commanders):
            raise DiscoveryError("Commander source facts are unavailable.", 503)
        color_identity = sorted(
            {item for row in colors for item in cast(list[str], _json(row["colors"]) or [])}
        )
        oracle_rows = await conn.fetch(
            "SELECT c.oracle_id FROM cards c WHERE c.id=ANY($1::uuid[])", commanders
        )
        return color_identity, [row["oracle_id"] for row in oracle_rows]

    def _match(self, row: asyncpg.Record) -> StrategyMatch:
        facts = _json(row["source_facts"])
        assert isinstance(facts, dict)
        evidence = []
        raw_evidence = _json(row["evidence"])
        if not isinstance(raw_evidence, list):
            raise RuntimeError("Discover match evidence was malformed")
        for item in raw_evidence:
            if not isinstance(item, dict):
                raise RuntimeError("Discover match evidence was malformed")
            relation = item["relation"]
            evidence.append(
                StrategyMatchEvidence(
                    query_purpose=item["query_purpose"],
                    criterion_type="printed_keyword" if relation == "keyword" else "oracle_tag",
                    criterion_id=UUID(item["criterion_id"]) if item["criterion_id"] else None,
                    criterion_label=item["criterion_label"],
                    matched_tag_id=UUID(item["matched_tag_id"]) if item["matched_tag_id"] else None,
                    matched_tag_label=item["matched_tag_label"],
                    relation=relation,
                )
            )
        return StrategyMatch(
            oracle_id=row["oracle_id"],
            name=row["name"],
            image_uri=safe_uri(row["image_uri"]),
            mana_cost=facts.get("mana_cost"),
            type_line=facts.get("type_line"),
            oracle_text=facts.get("oracle_text"),
            keywords=facts.get("keywords") or [],
            match_count=row["match_count"],
            global_popularity_rank=row["global_popularity_rank"],
            evidence=evidence,
        )

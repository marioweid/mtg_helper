"""Owner-scoped Scryfall tag matching for New Cards."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from uuid import UUID

import asyncpg

from mtg_helper.models.new_cards import CardFacts, NewCardMatch, NewCardsResponse, TagMatch

_SOURCE_MAX_AGE = timedelta(days=2)


class NewCardsError(ValueError):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class Owner:
    account_id: UUID
    email: str


def json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def price_cents(raw: Any) -> int | None:
    """Keep missing or malformed EUR prices unknown rather than presenting them as free."""
    try:
        prices = json_value(raw)
        if not isinstance(prices, dict):
            return None
        value = Decimal(str(prices.get("eur")))
        return int(round(value * 100)) if value.is_finite() and value >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


async def owned_deck(
    conn: asyncpg.Connection, owner: Owner, deck_id: UUID, *, lock: bool = False
) -> asyncpg.Record:
    """Load exactly one deck belonging to the authenticated account."""
    suffix = " FOR UPDATE" if lock else ""
    deck = await conn.fetchrow(
        "SELECT * FROM decks WHERE id = $1 AND lower(owner_email) = $2" + suffix,
        deck_id,
        owner.email.strip().lower(),
    )
    if deck is None:
        raise NewCardsError("Deck not found", 404)
    return deck


@dataclass(slots=True)
class MatchCandidate:
    row: asyncpg.Record
    facts: CardFacts
    tag_matches: list[TagMatch]

    @property
    def oracle_id(self) -> UUID:
        return self.facts.oracle_id

    def response(self) -> NewCardMatch:
        """Expose source card facts and tag provenance without inferred synergy."""
        facts = self.facts.model_dump(
            exclude={"oracle_id", "game_changer", "color_identity", "commander_legality", "layout"}
        )
        return NewCardMatch(
            **facts,
            oracle_id=self.oracle_id,
            card_id=self.row["id"],
            scryfall_id=self.row["scryfall_id"],
            image_uri=self.row["image_uri"],
            scryfall_uri=f"https://scryfall.com/search?q=oracleid%3A{self.oracle_id}",
            released_at=self.row["released_at"],
            expires_at=self.row["released_at"] + timedelta(days=60),
            price_eur_cents=price_cents(self.row["prices"]),
            matching_tag_count=self.row["matching_tag_count"],
            tag_matches=self.tag_matches,
        )


@dataclass(slots=True)
class DeckState:
    candidates: list[MatchCandidate]
    catalog: asyncpg.Record | None
    tags: asyncpg.Record | None
    dismissed: int
    status: str
    error: str | None

    def response(self) -> NewCardsResponse:
        """Render a truthful source state; never turn absent source facts into no matches."""
        stale = self.status == "source_stale"
        return NewCardsResponse(
            status=cast(
                Literal["ready", "unavailable", "source_stale", "source_mismatched"], self.status
            ),
            catalog_updated_at=self.catalog["published_at"] if self.catalog else None,
            tag_updated_at=self.tags["published_at"] if self.tags else None,
            stale=stale,
            eligible_count=len(self.candidates),
            dismissed_count=self.dismissed,
            error=self.error,
            matches=[candidate.response() for candidate in self.candidates]
            if self.status == "ready"
            else [],
        )


async def load(conn: asyncpg.Connection, owner: Owner, deck: asyncpg.Record) -> DeckState:
    """Load current eligible tag matches and their direct source provenance."""
    catalog = await conn.fetchrow("SELECT * FROM new_card_catalog_state WHERE singleton")
    tags = await conn.fetchrow("SELECT * FROM scryfall_tag_state WHERE singleton")
    status, error = _source_status(catalog, tags)
    dismissed = await conn.fetchval(
        "SELECT count(*) FROM new_card_dismissals WHERE deck_id = $1 AND account_id = $2",
        deck["id"],
        owner.account_id,
    )
    if status != "ready":
        return DeckState([], catalog, tags, dismissed, status, error)
    commander_ids = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
    commander_oracles = await _commander_oracles(conn, commander_ids)
    if len(commander_oracles) != len(commander_ids):
        return DeckState(
            [], catalog, tags, dismissed, "unavailable", "Commander source facts are unavailable."
        )
    commander_tags = await _commander_tags(conn, commander_oracles)
    if not commander_tags:
        return DeckState(
            [], catalog, tags, dismissed, "unavailable", "Commander Scryfall tags are unavailable."
        )
    candidates = await _matching_candidates(conn, deck, owner, commander_oracles, commander_tags)
    return DeckState(candidates, catalog, tags, dismissed, "ready", None)


def _source_status(
    catalog: asyncpg.Record | None, tags: asyncpg.Record | None
) -> tuple[str, str | None]:
    if catalog is None or tags is None:
        return (
            "unavailable",
            "Scryfall card or tag sources are unavailable. Run Admin Scryfall sync.",
        )
    if catalog["source_sha256"] != tags["source_sha256"]:
        return "source_mismatched", "Scryfall card and tag sources are from different generations."
    now = datetime.now(UTC)
    if (
        now - catalog["published_at"] > _SOURCE_MAX_AGE
        or now - tags["published_at"] > _SOURCE_MAX_AGE
    ):
        return "source_stale", "Scryfall card or tag sources are stale. Run Admin Scryfall sync."
    return "ready", None


async def _commander_oracles(conn: asyncpg.Connection, ids: list[UUID]) -> list[UUID]:
    rows = await conn.fetch(
        "SELECT c.oracle_id FROM unnest($1::uuid[]) WITH ORDINALITY d(id, position) "
        "JOIN cards c ON c.id = d.id "
        "JOIN new_card_catalog n ON n.oracle_id = c.oracle_id "
        "AND n.generation = (SELECT generation FROM new_card_catalog_state WHERE singleton) "
        "ORDER BY d.position",
        ids,
    )
    return [row["oracle_id"] for row in rows]


async def _commander_tags(conn: asyncpg.Connection, oracles: list[UUID]) -> list[UUID]:
    rows = await conn.fetch(
        "SELECT oracle_id, tag_id FROM scryfall_tag_memberships WHERE oracle_id = ANY($1::uuid[])",
        oracles,
    )
    if {row["oracle_id"] for row in rows} != set(oracles):
        return []
    return sorted({row["tag_id"] for row in rows})


async def _matching_candidates(
    conn: asyncpg.Connection,
    deck: asyncpg.Record,
    owner: Owner,
    commander_oracles: list[UUID],
    commander_tags: list[UUID],
) -> list[MatchCandidate]:
    colors = await _commander_colors(conn, commander_oracles)
    rows = await conn.fetch(
        """
        WITH matched AS (
            SELECT DISTINCT ct.tag_id AS commander_tag_id, cm.tag_id AS candidate_tag_id,
                c.id, c.scryfall_id, c.image_uri, c.prices, n.oracle_id, n.facts,
                n.released_at, c.name
            FROM unnest($1::uuid[]) AS ct(tag_id)
            JOIN scryfall_tag_descendants d ON d.ancestor_id = ct.tag_id
            JOIN scryfall_tag_memberships cm ON cm.tag_id = d.descendant_id
            JOIN new_card_catalog n ON n.oracle_id = cm.oracle_id
            JOIN new_card_catalog_state state ON state.generation = n.generation
            JOIN LATERAL (
                SELECT printed.* FROM cards printed
                WHERE printed.oracle_id = n.oracle_id AND printed.is_canonical
                ORDER BY printed.id LIMIT 1
            ) c ON true
            WHERE n.released_at <= $2 AND n.released_at > $2::date - 60
              AND n.facts->>'commander_legality' = 'legal'
              AND c.legalities->>'commander' = 'legal'
              AND c.color_identity <@ $3::text[]
              AND n.oracle_id <> ALL($4::uuid[])
              AND NOT EXISTS (
                  SELECT 1 FROM deck_cards dc JOIN cards owned ON owned.id = dc.card_id
                  WHERE dc.deck_id = $5 AND owned.oracle_id = n.oracle_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM deck_card_plans p JOIN cards planned ON planned.id = p.card_id
                  WHERE p.deck_id = $5 AND p.direction = 'addition'
                    AND planned.oracle_id = n.oracle_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM new_card_dismissals dismissed
                  WHERE dismissed.deck_id = $5 AND dismissed.account_id = $6
                    AND dismissed.oracle_id = n.oracle_id
              )
        )
        SELECT matched.id, matched.scryfall_id, matched.image_uri, matched.prices,
            matched.oracle_id, matched.facts, matched.released_at, matched.name,
            count(DISTINCT matched.commander_tag_id)::integer AS matching_tag_count,
            jsonb_agg(DISTINCT jsonb_build_object(
                'commander_tag_id', matched.commander_tag_id,
                'commander_tag_label',
                    COALESCE(commander_tag.metadata->>'label', commander_tag.slug),
                'candidate_tag_id', matched.candidate_tag_id,
                'candidate_tag_label',
                    COALESCE(candidate_tag.metadata->>'label', candidate_tag.slug),
                'relation', CASE WHEN matched.commander_tag_id = matched.candidate_tag_id
                    THEN 'direct' ELSE 'descendant' END
            )) AS tag_matches
        FROM matched
        JOIN scryfall_tags commander_tag ON commander_tag.id = matched.commander_tag_id
        JOIN scryfall_tags candidate_tag ON candidate_tag.id = matched.candidate_tag_id
        GROUP BY matched.id, matched.scryfall_id, matched.image_uri, matched.prices,
            matched.oracle_id, matched.facts, matched.released_at, matched.name
        ORDER BY matching_tag_count DESC, matched.released_at DESC, matched.name, matched.oracle_id
        """,
        commander_tags,
        datetime.now(UTC).date(),
        colors,
        commander_oracles,
        deck["id"],
        owner.account_id,
    )
    return [
        MatchCandidate(
            row,
            CardFacts.model_validate(json_value(row["facts"])),
            [TagMatch.model_validate(item) for item in json_value(row["tag_matches"])],
        )
        for row in rows
    ]


async def _commander_colors(conn: asyncpg.Connection, oracles: list[UUID]) -> list[str]:
    rows = await conn.fetch(
        "SELECT facts->'color_identity' AS colors FROM new_card_catalog "
        "WHERE oracle_id = ANY($1::uuid[]) AND generation = "
        "(SELECT generation FROM new_card_catalog_state WHERE singleton)",
        oracles,
    )
    return sorted({color for row in rows for color in json_value(row["colors"])})

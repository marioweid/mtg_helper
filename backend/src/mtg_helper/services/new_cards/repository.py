"""Owner-scoped, live-filtered catalog/context reads for the experimental pilot."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import asyncpg

from mtg_helper.models.new_cards import CardFacts, NewCardPick, NewCardsResponse
from mtg_helper.services.agents._model import OPENAI_MODEL
from mtg_helper.services.new_cards.evaluator import VERSION, Assessment, fingerprint


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


@dataclass(slots=True)
class Candidate:
    row: asyncpg.Record
    facts: CardFacts
    input_hash: str

    @property
    def oracle_id(self) -> UUID:
        return self.facts.oracle_id

    def pick(self, assessment: Assessment) -> NewCardPick:
        facts = self.facts.model_dump(
            exclude={"oracle_id", "game_changer", "color_identity", "commander_legality", "layout"}
        )
        return NewCardPick(
            **facts,
            **assessment.model_dump(),
            oracle_id=self.oracle_id,
            card_id=self.row["id"],
            scryfall_id=self.row["scryfall_id"],
            image_uri=self.row["image_uri"],
            scryfall_uri=f"https://scryfall.com/search?q=oracleid%3A{self.oracle_id}",
            released_at=self.row["released_at"],
            expires_at=self.row["released_at"] + timedelta(days=60),
            price_eur_cents=price_cents(self.row["prices"]),
        )


@dataclass(slots=True)
class DeckState:
    context: dict[str, Any]
    candidates: list[Candidate]
    cached: dict[UUID, asyncpg.Record]
    catalog: asyncpg.Record | None
    job: asyncpg.Record | None
    dismissed: int
    ready: bool

    def valid(self, candidate: Candidate) -> bool:
        cached = self.cached.get(candidate.oracle_id)
        return bool(cached and cached["input_hash"] == candidate.input_hash)

    def pending(self) -> list[Candidate]:
        return [candidate for candidate in self.candidates if not self.valid(candidate)]

    def response(self) -> NewCardsResponse:
        """Render only currently eligible, exact-context assessments; never start work on reads."""
        now = datetime.now(UTC)
        picks = []
        assessed_times = []
        for candidate in self.candidates:
            if not self.valid(candidate):
                continue
            row = self.cached[candidate.oracle_id]
            assessment = Assessment.model_validate(json_value(row["assessment"]))
            assessed_times.append(row["assessed_at"])
            if assessment.label != "reject":
                picks.append(candidate.pick(assessment))
        result = NewCardsResponse(
            catalog_updated_at=self.catalog["published_at"] if self.catalog else None,
            analyzed_at=max(assessed_times, default=None),
            eligible_count=len(self.candidates),
            assessed_count=len(assessed_times),
            remaining_count=len(self.candidates) - len(assessed_times),
            dismissed_count=self.dismissed,
            picks=picks,
        )
        result.stale = bool(self.catalog and now - self.catalog["published_at"] > timedelta(days=2))
        result.stale |= any(
            c.oracle_id in self.cached and not self.valid(c) for c in self.candidates
        )
        if not self.ready:
            result.status = "unavailable"
            result.error = (
                "Run Admin card sync to populate complete release history and deck facts."
            )
        elif self.job:
            _job_status(result, self.job, now)
        return result


def _job_status(result: NewCardsResponse, job: asyncpg.Record, now: datetime) -> None:
    if job["token"] is not None:
        if job["lease_until"] > now:
            result.status = "running"
        else:
            result.status = "error"
            result.error = "Analysis was interrupted. Retry to assess the remaining cards."
    elif job["error"]:
        result.status = "error"
        result.error = job["error"]


async def owned_deck(
    conn: asyncpg.Connection,
    owner: Owner,
    deck_id: UUID,
    *,
    lock: bool = False,
) -> asyncpg.Record:
    suffix = " FOR UPDATE" if lock else ""
    deck = await conn.fetchrow(
        "SELECT * FROM decks WHERE id = $1 AND lower(owner_email) = $2" + suffix,
        deck_id,
        owner.email.strip().lower(),
    )
    if deck is None:
        raise NewCardsError("Deck not found", 404)
    return deck


async def _context(
    conn: asyncpg.Connection, owner: Owner, deck: asyncpg.Record
) -> tuple[dict, bool]:
    commanders = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
    rows = await conn.fetch(
        """
        SELECT c.id, c.oracle_id, n.facts, COALESCE(dc.quantity, 1) AS quantity,
               COALESCE(p.direction = 'cut', false) AS pending_cut
        FROM cards c LEFT JOIN deck_cards dc ON dc.card_id = c.id AND dc.deck_id = $1
        LEFT JOIN deck_card_plans p ON p.card_id = c.id AND p.deck_id = $1
        LEFT JOIN new_card_catalog n ON n.oracle_id = c.oracle_id
            AND n.generation = (SELECT generation FROM new_card_catalog_state WHERE singleton)
        WHERE dc.deck_id = $1 OR c.id = ANY($2::uuid[])
        ORDER BY c.oracle_id, c.id
        """,
        deck["id"],
        commanders,
    )
    physical = []
    for row in rows:
        if row["facts"] is not None:
            physical.append(
                json_value(row["facts"])
                | {
                    "quantity": row["quantity"],
                    "pending_cut": row["pending_cut"],
                    "commander": row["id"] in commanders,
                }
            )
    plans = await conn.fetch(
        "SELECT c.name, p.direction, p.quantity FROM deck_card_plans p "
        "JOIN cards c ON c.id = p.card_id WHERE p.deck_id = $1 ORDER BY c.name, p.direction",
        deck["id"],
    )
    preferences = await conn.fetch(
        "SELECT p.preference_type, p.description, c.name FROM preferences p "
        "LEFT JOIN cards c ON c.id = p.card_id WHERE p.account_id = $1 "
        "ORDER BY p.preference_type, c.name, p.description",
        owner.account_id,
    )
    notes = await conn.fetchval(
        "SELECT notes FROM deck_coach_memory WHERE deck_id = $1 AND account_id = $2",
        deck["id"],
        owner.account_id,
    )
    context = {
        "physical": physical,
        "name": deck["name"],
        "description": deck["description"],
        "bracket": deck["bracket"],
        "themes": list(deck["archetype_tags"]),
        "role_targets": json_value(deck["stage_targets"]),
        "notes": notes or "",
        "preferences": [dict(p) for p in preferences],
        "planned_changes": [dict(p) for p in plans],
    }
    return context, len(physical) == len(rows) and len(rows) >= len(commanders)


async def _candidates(
    conn: asyncpg.Connection,
    owner: Owner,
    deck_id: UUID,
    colors: list[str],
) -> list[asyncpg.Record]:
    return list(
        await conn.fetch(
            """
        SELECT c.id, c.scryfall_id, n.oracle_id, c.image_uri, c.prices, n.facts, n.released_at
        FROM new_card_catalog n
        JOIN new_card_catalog_state s ON s.generation = n.generation
        JOIN LATERAL (
            SELECT c.* FROM cards c WHERE c.oracle_id = n.oracle_id AND c.is_canonical
            ORDER BY c.id LIMIT 1
        ) c ON true
        WHERE n.released_at <= $4 AND n.released_at > $4::date - 60
          AND n.facts->>'commander_legality' = 'legal'
          AND c.legalities->>'commander' = 'legal' AND c.color_identity <@ $3::text[]
          AND NOT EXISTS (
              SELECT 1 FROM deck_cards dc JOIN cards pc ON pc.id = dc.card_id
              WHERE dc.deck_id = $1 AND pc.oracle_id = n.oracle_id)
          AND NOT EXISTS (
              SELECT 1 FROM decks d JOIN cards pc ON pc.id IN (d.commander_id, d.partner_id)
              WHERE d.id = $1 AND pc.oracle_id = n.oracle_id)
          AND NOT EXISTS (
              SELECT 1 FROM deck_card_plans p JOIN cards pc ON pc.id = p.card_id
              WHERE p.deck_id = $1 AND p.direction = 'addition' AND pc.oracle_id = n.oracle_id)
          AND NOT EXISTS (
              SELECT 1 FROM new_card_dismissals x
              WHERE x.deck_id = $1 AND x.account_id = $2 AND x.oracle_id = n.oracle_id)
          AND NOT EXISTS (
              SELECT 1 FROM preferences p JOIN cards pc ON pc.id = p.card_id
              WHERE p.account_id = $2 AND p.preference_type = 'avoid_card'
                AND pc.oracle_id = n.oracle_id)
        ORDER BY n.released_at DESC, c.name, n.oracle_id
        """,
            deck_id,
            owner.account_id,
            colors,
            datetime.now(UTC).date(),
        )
    )


async def load(conn: asyncpg.Connection, owner: Owner, deck: asyncpg.Record) -> DeckState:
    """Load one owner's context and live candidate exclusions within the caller's transaction."""
    context, ready = await _context(conn, owner, deck)
    colors = sorted(
        {
            color
            for card in context["physical"]
            if card["commander"]
            for color in card["color_identity"]
        }
    )
    context_hash = fingerprint({"deck": context, "model": OPENAI_MODEL, "version": VERSION})
    rows = await _candidates(conn, owner, deck["id"], colors)
    candidates = []
    for row in rows:
        facts = CardFacts.model_validate(json_value(row["facts"]))
        if set(facts.color_identity) <= set(colors):
            candidates.append(
                Candidate(
                    row,
                    facts,
                    fingerprint(
                        {
                            "context": context_hash,
                            "candidate": facts.model_dump(mode="json"),
                            "release": row["released_at"],
                        }
                    ),
                )
            )
    cache = await conn.fetch(
        "SELECT * FROM new_card_assessments WHERE deck_id = $1 AND account_id = $2",
        deck["id"],
        owner.account_id,
    )
    catalog = await conn.fetchrow("SELECT * FROM new_card_catalog_state WHERE singleton")
    job = await conn.fetchrow(
        "SELECT * FROM new_card_jobs WHERE account_id = $1 AND deck_id = $2",
        owner.account_id,
        deck["id"],
    )
    dismissed = await conn.fetchval(
        "SELECT count(*) FROM new_card_dismissals WHERE deck_id = $1 AND account_id = $2",
        deck["id"],
        owner.account_id,
    )
    return DeckState(
        context,
        candidates,
        {r["oracle_id"]: r for r in cache},
        catalog,
        job,
        dismissed,
        ready and catalog is not None,
    )

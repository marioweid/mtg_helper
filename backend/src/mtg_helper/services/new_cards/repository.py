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
    constellation_key: str
    context: dict[str, Any]
    commander_oracle_ids: list[UUID]
    candidates: list[Candidate]
    cached: dict[UUID, asyncpg.Record]
    catalog: asyncpg.Record | None
    job: asyncpg.Record | None
    dismissed: int
    hidden: set[UUID]
    ready: bool

    def valid(self, candidate: Candidate) -> bool:
        cached = self.cached.get(candidate.oracle_id)
        return bool(cached and cached["input_hash"] == candidate.input_hash)

    def pending(self) -> list[Candidate]:
        return [candidate for candidate in self.candidates if not self.valid(candidate)]

    def response(self) -> NewCardsResponse:
        """Render only currently eligible, exact-context assessments; never start work on reads."""
        now = datetime.now(UTC)
        stale = bool(self.catalog and now - self.catalog["published_at"] > timedelta(days=2))
        picks, assessed_times = self._assessments()
        complete = len(assessed_times) == len(self.candidates)
        result = NewCardsResponse(
            catalog_updated_at=self.catalog["published_at"] if self.catalog else None,
            analyzed_at=max(assessed_times, default=None),
            eligible_count=len(self.candidates),
            assessed_count=len(assessed_times),
            remaining_count=len(self.candidates) - len(assessed_times),
            dismissed_count=self.dismissed,
            picks=picks if self.ready and complete and not stale else [],
        )
        _set_status(result, ready=self.ready, stale=stale, complete=complete, job=self.job, now=now)
        return result

    def _assessments(self) -> tuple[list[NewCardPick], list[datetime]]:
        """Return visible picks and assessment timestamps for current candidates only."""
        picks: list[NewCardPick] = []
        assessed_times: list[datetime] = []
        for candidate in self.candidates:
            if not self.valid(candidate):
                continue
            row = self.cached[candidate.oracle_id]
            assessment = Assessment.model_validate(json_value(row["assessment"]))
            assessed_times.append(row["assessed_at"])
            if assessment.label != "reject":
                if candidate.oracle_id not in self.hidden:
                    picks.append(candidate.pick(assessment))
        return picks, assessed_times


def _set_status(
    result: NewCardsResponse,
    *,
    ready: bool,
    stale: bool,
    complete: bool,
    job: asyncpg.Record | None,
    now: datetime,
) -> None:
    """Set the read-model status, preserving ``idle`` for completed checks."""
    result.stale = stale
    if not ready:
        result.status = "unavailable"
        result.error = "Run Admin card sync to populate complete release history and deck facts."
    elif stale:
        result.status = "source_stale"
        result.error = "Card sources are too old for a current complete result."
    elif not complete:
        if job:
            _job_status(result, job, now)
        else:
            result.status = "waiting"


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
    else:
        result.status = "waiting"


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
) -> tuple[dict, bool, list[UUID]]:
    commanders = [deck["commander_id"]] + ([deck["partner_id"]] if deck["partner_id"] else [])
    rows = await conn.fetch(
        """
        SELECT c.id, c.oracle_id, n.facts
        FROM cards c
        LEFT JOIN new_card_catalog n ON n.oracle_id = c.oracle_id
            AND n.generation = (SELECT generation FROM new_card_catalog_state WHERE singleton)
        WHERE c.id = ANY($1::uuid[])
        ORDER BY array_position($1::uuid[], c.id)
        """,
        commanders,
    )
    commander_facts = []
    for row in rows:
        if row["facts"] is not None:
            commander_facts.append(json_value(row["facts"]))
    commander_oracle_ids = [row["oracle_id"] for row in rows]
    ready = len(commander_facts) == len(commanders) and len(commander_oracle_ids) == len(commanders)
    return {"commanders": commander_facts}, ready, commander_oracle_ids


async def _candidates(
    conn: asyncpg.Connection,
    colors: list[str],
    commander_oracles: list[UUID],
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
        WHERE n.released_at <= $2 AND n.released_at > $2::date - 60
          AND n.facts->>'commander_legality' = 'legal'
           AND c.legalities->>'commander' = 'legal' AND c.color_identity <@ $3::text[]
          AND n.oracle_id <> ALL($1::uuid[])
        ORDER BY n.released_at DESC, c.name, n.oracle_id
        """,
            commander_oracles,
            datetime.now(UTC).date(),
            colors,
        )
    )


async def load(conn: asyncpg.Connection, owner: Owner, deck: asyncpg.Record) -> DeckState:
    """Load one owner's context and live candidate exclusions within the caller's transaction."""
    context, ready, commander_oracle_ids = await _context(conn, owner, deck)
    colors = sorted({color for card in context["commanders"] for color in card["color_identity"]})
    constellation_key = fingerprint({"commanders": [str(value) for value in commander_oracle_ids]})
    context_hash = fingerprint({"commanders": context, "model": OPENAI_MODEL, "version": VERSION})
    rows = await _candidates(conn, colors, commander_oracle_ids)
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
        "SELECT * FROM new_card_shared_assessments WHERE constellation_key = $1", constellation_key
    )
    catalog = await conn.fetchrow("SELECT * FROM new_card_catalog_state WHERE singleton")
    job = await conn.fetchrow(
        "SELECT * FROM new_card_claims WHERE constellation_key = $1", constellation_key
    )
    dismissed = await conn.fetchval(
        "SELECT count(*) FROM new_card_dismissals WHERE deck_id = $1 AND account_id = $2",
        deck["id"],
        owner.account_id,
    )
    hidden_rows = await conn.fetch(
        """
        SELECT c.oracle_id FROM deck_cards dc JOIN cards c ON c.id = dc.card_id
        WHERE dc.deck_id = $1
        UNION
        SELECT c.oracle_id FROM deck_card_plans p JOIN cards c ON c.id = p.card_id
        WHERE p.deck_id = $1 AND p.direction = 'addition'
        UNION
        SELECT oracle_id FROM new_card_dismissals WHERE deck_id = $1 AND account_id = $2
        """,
        deck["id"],
        owner.account_id,
    )
    return DeckState(
        constellation_key,
        context,
        commander_oracle_ids,
        candidates,
        {r["oracle_id"]: r for r in cache},
        catalog,
        job,
        dismissed,
        {row["oracle_id"] for row in hidden_rows},
        ready and catalog is not None,
    )

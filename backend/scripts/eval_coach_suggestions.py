"""Evaluate Commander Coach suggestions against Moxfield-derived benchmark decks.

Moxfield is used only to construct benchmark decklists and removal sets. The
Coach pipeline under test must not query Moxfield for suggestions.
"""

import argparse
import asyncio
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession

from mtg_helper.models.ai import CommanderCoachRequest
from mtg_helper.models.decks import CommanderCardSummary, DeckCardItem, DeckDetailResponse
from mtg_helper.services import moxfield_recs_service
from mtg_helper.services.commander_coach.orchestrator import run_coach

_DEFAULT_DB = "postgresql://mtg:mtg_dev@localhost:5432/mtg_helper"
_COMMANDERS = {
    "camellia": {
        "name": "Camellia, the Seedmiser",
        "tags": ["food_matters", "squirrel_tribal", "aristocrats", "sacrifice"],
        "message": "Suggest strong general upgrades for this Food Squirrel aristocrats deck.",
    },
    "zaxara": {
        "name": "Zaxara, the Exemplary",
        "tags": ["x_spells", "hydra_tribal", "ramp"],
        "message": "Suggest strong general upgrades for this X-spells Hydra deck.",
    },
}


@dataclass(frozen=True)
class EvalConfig:
    """Runtime options for one evaluation run."""

    database_url: str
    commander_key: str
    top_decks: int
    remove_count: int
    seed: int


async def main() -> None:
    """Run the CLI entrypoint."""
    args = _parse_args()
    config = EvalConfig(
        database_url=args.database_url,
        commander_key=args.commander,
        top_decks=args.top_decks,
        remove_count=args.remove_count,
        seed=args.seed,
    )
    result = await run_eval(config)
    print(json.dumps(result, indent=2, default=str))


async def run_eval(config: EvalConfig) -> dict[str, object]:
    """Run benchmark decks for one commander and return aggregate metrics."""
    commander_cfg = _COMMANDERS[config.commander_key]
    pool = await asyncpg.create_pool(config.database_url)
    try:
        commander = await _commander_row(pool, commander_cfg["name"])
        decks = await _top_decks(commander)
        runs = []
        for index, deck_summary in enumerate(decks[: config.top_decks], start=1):
            runs.append(
                await _eval_one(pool, commander, commander_cfg, deck_summary, config, index)
            )
        total_hits = sum(run["hit_count"] for run in runs)
        total_removed = sum(len(run["removed"]) for run in runs)
        return {
            "commander": commander_cfg["name"],
            "top_decks": len(runs),
            "remove_count": config.remove_count,
            "total_hits": total_hits,
            "total_removed": total_removed,
            "exact_hit_rate": total_hits / total_removed if total_removed else 0.0,
            "runs": runs,
        }
    finally:
        await pool.close()


async def _eval_one(
    pool: asyncpg.Pool,
    commander: asyncpg.Record,
    commander_cfg: dict[str, object],
    deck_summary: dict[str, object],
    config: EvalConfig,
    index: int,
) -> dict[str, object]:
    cards = await _benchmark_cards(pool, commander_cfg["name"], str(deck_summary["id"]))
    removable = [card for card in cards if card.name not in {"Sol Ring", "Arcane Signet"}]
    removed = random.Random(config.seed + index).sample(
        removable,
        min(config.remove_count, len(removable)),
    )
    removed_names = {card.name for card in removed}
    kept = [card for card in cards if card.name not in removed_names]
    deck = _deck_response(commander, commander_cfg, kept)
    response = await run_coach(
        pool,
        deck,
        CommanderCoachRequest(message=str(commander_cfg["message"]), mode="doctor"),
    )
    recommended = _recommended_names(response.doctor)
    hits = sorted(removed_names & set(recommended))
    return {
        "deck_id": deck_summary["id"],
        "likes": deck_summary["likes"],
        "removed": sorted(removed_names),
        "recommended": recommended,
        "hits": hits,
        "hit_count": len(hits),
    }


async def _commander_row(pool: asyncpg.Pool, name: str) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM cards WHERE name = $1", name)
    if row is None:
        raise RuntimeError(f"Commander not found: {name}")
    return row


async def _top_decks(commander: asyncpg.Record) -> list[dict[str, object]]:
    async with CurlAsyncSession(impersonate="chrome", timeout=30) as client:
        card_id = await moxfield_recs_service.fetch_moxfield_card_id(
            str(commander["scryfall_id"]), commander["name"], client=client
        )
        if card_id is None:
            return []
        return await moxfield_recs_service.fetch_top_decks(card_id, client=client)


async def _benchmark_cards(
    pool: asyncpg.Pool,
    commander_name: object,
    deck_id: str,
) -> list[DeckCardItem]:
    async with CurlAsyncSession(impersonate="chrome", timeout=30) as client:
        entries = await moxfield_recs_service.fetch_deck_card_entries(deck_id, client=client)
    mapping, quantities = await _resolve_entries(entries)
    rows = await _rows_by_oracle(pool, list(set(mapping.values())))
    return [
        _deck_item(rows[oracle_id], quantities[scryfall_id])
        for scryfall_id, oracle_id in mapping.items()
        if oracle_id in rows and rows[oracle_id]["name"] != commander_name
    ]


async def _resolve_entries(
    entries: list[dict[str, object]],
) -> tuple[dict[str, str], dict[str, int]]:
    ids = list({str(entry["scryfall_id"]).lower() for entry in entries})
    quantities = {str(entry["scryfall_id"]).lower(): int(entry["quantity"]) for entry in entries}
    async with httpx.AsyncClient(timeout=30) as client:
        mapping = await moxfield_recs_service._resolve_oracle_ids(ids, client=client)
    return mapping, quantities


async def _rows_by_oracle(pool: asyncpg.Pool, oracle_ids: list[str]) -> dict[str, asyncpg.Record]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
                   color_identity, image_uri, rarity, tags,
                   ROUND((prices->>'eur')::numeric * 100)::integer AS price_eur_cents
            FROM cards WHERE oracle_id = ANY($1::uuid[])
            """,
            oracle_ids,
        )
    return {str(row["oracle_id"]).lower(): row for row in rows}


def _deck_item(row: asyncpg.Record, quantity: int) -> DeckCardItem:
    return DeckCardItem(
        deck_card_id=uuid4(),
        card_id=row["id"],
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        mana_cost=row["mana_cost"],
        cmc=row["cmc"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        image_uri=row["image_uri"],
        rarity=row["rarity"],
        quantity=quantity,
        categories=[],
        added_by="user",
        ai_reasoning=None,
        qualifying_stages=[],
        tags=list(row["tags"] or []),
        price_eur_cents=row["price_eur_cents"],
    )


def _deck_response(
    commander: asyncpg.Record,
    commander_cfg: dict[str, object],
    cards: list[DeckCardItem],
) -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_card = CommanderCardSummary(
        id=commander["id"],
        name=commander["name"],
        mana_cost=commander["mana_cost"],
        cmc=commander["cmc"],
        type_line=commander["type_line"],
        oracle_text=commander["oracle_text"],
        color_identity=list(commander["color_identity"] or []),
        tags=list(commander["tags"] or []),
    )
    return DeckDetailResponse(
        id=uuid4(),
        name=f"Eval {commander['name']}",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander["id"],
        partner_id=None,
        commander_color_identity=list(commander["color_identity"] or []),
        commander_card=commander_card,
        partner_card=None,
        owner_email="eval@example.com",
        created_at=now,
        updated_at=now,
        archetype_tags=list(commander_cfg["tags"]),
        cards=cards,
    )


def _recommended_names(doctor: object) -> list[str]:
    if doctor is None:
        return []
    names = [add.card.name for add in doctor.adds]
    for swap in doctor.swaps:
        names.extend(card.name for card in swap.add)
    return list(dict.fromkeys(names))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=_DEFAULT_DB)
    parser.add_argument("--commander", choices=sorted(_COMMANDERS), default="camellia")
    parser.add_argument("--top-decks", type=int, default=5)
    parser.add_argument("--remove-count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260622)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main())

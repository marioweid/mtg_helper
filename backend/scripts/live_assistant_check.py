"""Live end-to-end check of the MTG Assistant against a real Moxfield deck.

Imports the deck locally (or reuses an existing import with the same name),
loads it through the standard deck-service path (with fit scoring), runs the
single MTG Assistant turn, and prints the full structured response.

Usage (from backend/):
    uv run python scripts/live_assistant_check.py \
        --url https://moxfield.com/decks/hCagAYMsLn65FeAQDcTiWQ \
        --bracket 3 \
        --message "What do I need to cut and what to add to make this an
                   aristocrats deck?"
"""

import argparse
import asyncio
import json

import asyncpg

from mtg_helper.config import settings
from mtg_helper.models.ai import CommanderCoachRequest
from mtg_helper.services import deck_service
from mtg_helper.services.commander_coach.orchestrator import run_coach
from mtg_helper.services.deck_url_import_service import import_from_url, parse_deck_url

_OWNER_EMAIL = "live-eval@mtg.local"


async def _find_or_import(
    pool: asyncpg.Pool,
    url: str,
    bracket: int,
) -> dict[str, object]:
    source, deck_id = parse_deck_url(url)
    if source == "moxfield":
        from curl_cffi.requests import AsyncSession as CurlAsyncSession

        from mtg_helper.services.deck_url_import_service import fetch_moxfield_deck

        async with CurlAsyncSession(impersonate="chrome", timeout=30) as client:
            raw = await fetch_moxfield_deck(deck_id, client=client)
        commanders = raw.commanders
    else:
        commanders = []
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT d.id FROM decks d
            JOIN cards c ON c.id = d.commander_id
            WHERE lower(d.owner_email) = $1
              AND c.name = $2
              AND EXISTS (SELECT 1 FROM deck_cards dc WHERE dc.deck_id = d.id)
            ORDER BY d.created_at DESC LIMIT 1
            """,
            _OWNER_EMAIL,
            commanders[0] if commanders else "",
        )
        if existing is not None:
            return {"deck_id": existing["id"], "reused": True}
    result = await import_from_url(pool, url, _OWNER_EMAIL, bracket=bracket)
    return {"deck_id": str(result.deck.id), "reused": False, "imported": result.imported_count}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--bracket", type=int, default=3)
    parser.add_argument("--message", required=True)
    parser.add_argument(
        "--max-deck-tokens", type=int, default=0, help="unused; kept for CLI compat"
    )
    args = parser.parse_args()

    pool = await asyncpg.create_pool(settings.database_url)
    try:
        info = await _find_or_import(pool, args.url, args.bracket)
        deck = await deck_service.get_deck(pool, info["deck_id"])
        if deck is None:
            raise SystemExit(f"Deck not found after import: {info['deck_id']}")

        result = await run_coach(
            pool,
            deck,
            CommanderCoachRequest(message=args.message),
        )
        payload = {
            "deck_id": str(info["deck_id"]),
            "deck_name": deck.name,
            "commander": deck.commander_card.name if deck.commander_card else None,
            "partner": deck.partner_card.name if deck.partner_card else None,
            "bracket": deck.bracket,
            "archetype_tags": deck.archetype_tags,
            "card_count": sum(card.quantity for card in deck.cards),
            "mode": result.mode,
            "reply": result.reply,
            "recommendations": [
                {
                    "name": option.card.name,
                    "role_match": option.role_match,
                    "reason": option.reason,
                    "tradeoff": option.tradeoff,
                }
                for option in result.recommendations
            ],
        }
        if result.doctor is not None:
            payload["doctor"] = {
                "summary": result.doctor.summary,
                "cuts": [
                    {"name": cut.card_name, "reason": cut.reason} for cut in result.doctor.cuts
                ],
                "adds": [
                    {"name": add.card.name, "reason": add.reason} for add in result.doctor.adds
                ],
                "swaps": [
                    {
                        "remove": swap.remove,
                        "add": [card.name for card in swap.add],
                        "reason": swap.reason,
                    }
                    for swap in result.doctor.swaps
                ],
            }
        if result.replacement is not None:
            payload["replacement"] = {
                "target_card_name": result.replacement.target_card_name,
                "summary": result.replacement.summary,
                "keep_reason": result.replacement.keep_reason,
                "best_pick": (
                    result.replacement.best_pick.name if result.replacement.best_pick else None
                ),
            }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

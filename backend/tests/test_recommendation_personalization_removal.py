"""Real recommendation outcomes ignore retained personalization records."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
from httpx import AsyncClient

from mtg_helper.models.recommendations import QueryPreview
from mtg_helper.services.new_cards import catalog
from mtg_helper.services.new_cards import repository as new_cards_repository
from mtg_helper.services.new_cards.discovery import release_history
from mtg_helper.services.recommendations import repository as discover_repository
from mtg_helper.services.recommendations.provider import Provider
from mtg_helper.services.recommendations.service import DiscoveryService
from mtg_helper.services.recommendations.source_repository import SourceRepository
from tests.conftest import create_test_deck


async def _card_ids(pool: asyncpg.Pool, names: list[str]) -> dict[str, UUID]:
    rows = await pool.fetch("SELECT id, name FROM cards WHERE name = ANY($1::text[])", names)
    return {row["name"]: row["id"] for row in rows}


async def _insert_card(
    pool: asyncpg.Pool,
    name: str,
    *,
    oracle_id: UUID | None = None,
    type_line: str = "Artifact",
    mana_cost: str = "{1}{G}",
    colors: list[str] | None = None,
    tags: list[str] | None = None,
    price: str = "1.00",
    canonical: bool = True,
) -> UUID:
    return await pool.fetchval(
        """
        INSERT INTO cards (scryfall_id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
            color_identity, colors, legalities, prices, tags, card_types, is_canonical)
        VALUES ($1, $2, $3, $4, 2, $5, $6, $7, $7, '{"commander":"legal"}'::jsonb,
            jsonb_build_object('eur', $8::text), $9, ARRAY[$10]::text[], $11)
        RETURNING id
        """,
        uuid4(),
        oracle_id or uuid4(),
        name,
        mana_cost,
        type_line,
        f"{name} supports the deck plan.",
        colors or ["G"],
        price,
        tags or [],
        type_line.split()[0],
        canonical,
    )


async def _publish_sources(pool: asyncpg.Pool, recent: set[UUID]) -> None:
    rows = await pool.fetch("SELECT * FROM cards WHERE is_canonical")
    now = datetime.now(UTC)
    old = (now - timedelta(days=500)).date().isoformat()
    current = (now - timedelta(days=1)).date().isoformat()
    sources = [
        dict(row)
        | {
            "object": "card",
            "id": str(row["scryfall_id"]),
            "oracle_id": str(row["oracle_id"]),
            "legalities": json.loads(row["legalities"]),
            "games": ["paper"],
            "released_at": current if row["id"] in recent else old,
            "set_type": "expansion",
            "reprint": False,
        }
        for row in rows
    ]
    async with pool.acquire() as conn, conn.transaction():
        await catalog.publish(conn, sources, release_history(sources), now)


async def _seed_retrieval_state(pool: asyncpg.Pool) -> dict[str, UUID]:
    ramp_a = await _insert_card(pool, "Seeded Ramp A", tags=["ramp"])
    ramp_b = await _insert_card(
        pool, "Seeded Ramp B", type_line="Enchantment", tags=["ramp"], price="2.00"
    )
    garden = await _insert_card(
        pool,
        "Seeded Garden",
        type_line="Land",
        mana_cost="",
        colors=["G", "W"],
        tags=["lands"],
    )
    pet = await _insert_card(pool, "Legacy Pet", type_line="Creature", tags=[])
    reprint = await _insert_card(
        pool, "Seeded Ramp A reprint", oracle_id=await _oracle(pool, ramp_a), canonical=False
    )
    ids = await _card_ids(pool, ["Doubling Season", "Forest", "Plains"])
    await pool.execute(
        "UPDATE cards SET tags = ARRAY['ramp'] WHERE id = $1", ids["Doubling Season"]
    )
    await pool.execute("UPDATE cards SET tags = ARRAY['lands'] WHERE id = $1", ids["Forest"])
    return {
        "doubling_season": ids["Doubling Season"],
        "plains": ids["Plains"],
        "ramp_a": ramp_a,
        "ramp_b": ramp_b,
        "garden": garden,
        "pet": pet,
        "reprint": reprint,
    }


async def _oracle(pool: asyncpg.Pool, card_id: UUID) -> UUID:
    oracle_id = await pool.fetchval("SELECT oracle_id FROM cards WHERE id = $1", card_id)
    assert isinstance(oracle_id, UUID)
    return oracle_id


async def _scryfall(pool: asyncpg.Pool, card_id: UUID) -> UUID:
    scryfall_id = await pool.fetchval("SELECT scryfall_id FROM cards WHERE id = $1", card_id)
    assert isinstance(scryfall_id, UUID)
    return scryfall_id


async def _outcomes(
    client: AsyncClient,
    pool: asyncpg.Pool,
    deck_id: UUID,
    owner: discover_repository.Owner,
    swap_id: UUID,
) -> dict[str, object]:
    build = await client.post(
        f"/api/v1/decks/{deck_id}/build", json={"stage": "ramp", "target": 10}
    )
    suggest = await client.post(
        f"/api/v1/decks/{deck_id}/suggest", json={"prompt": "ramp", "count": 10}
    )
    mana = await client.post(f"/api/v1/decks/{deck_id}/mana-fix")
    swap = await client.post(f"/api/v1/decks/{deck_id}/cards/{swap_id}/swap", json={"limit": 10})
    detail = await client.get(f"/api/v1/decks/{deck_id}")
    assert all(response.status_code == 200 for response in (build, suggest, mana, swap, detail))
    async with pool.acquire() as conn:
        deck = await new_cards_repository.owned_deck(conn, owner, deck_id)
        state = await new_cards_repository.load(conn, owner, deck)
    discover = await DiscoveryService(pool, SourceRepository(pool), Provider("test")).preview(
        owner, deck_id, QueryPreview(limit=50)
    )
    return {
        "build": _suggestion_ids(build.json()["data"]["suggestions"]),
        "build_sources": _sources_by_scryfall(build.json()["data"]["suggestions"]),
        "freeform": _suggestion_ids(suggest.json()["data"]["suggestions"]),
        "mana": _suggestion_ids(mana.json()["data"]["suggestions"]),
        "swap": _suggestion_ids(swap.json()["data"]["candidates"]),
        "fit": _fit(detail.json()["data"]["cards"]),
        "new_cards": [str(candidate.oracle_id) for candidate in state.candidates],
        "discover": [(str(card.oracle_id), card.excluded) for card in discover.cards],
    }


def _suggestion_ids(cards: list[dict[str, object]]) -> list[str]:
    return [str(card["scryfall_id"]) for card in cards]


def _sources_by_scryfall(cards: list[dict[str, object]]) -> dict[str, list[str]]:
    return {str(card["scryfall_id"]): list(card["sources"]) for card in cards}


def _fit(cards: list[dict[str, object]]) -> list[tuple[str, bool]]:
    return [(str(card["scryfall_id"]), bool(card["deck_fit_protected"])) for card in cards]


async def _seed_legacy_state(
    client: AsyncClient,
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    ids: dict[str, UUID],
) -> None:
    other_deck = UUID(await create_test_deck(client, name="Cross-deck legacy history"))
    await pool.execute(
        "INSERT INTO deck_cards (deck_id, card_id) VALUES ($1, $2)", other_deck, ids["ramp_b"]
    )
    await pool.executemany(
        "INSERT INTO preferences (account_id, preference_type, card_id, description) "
        "VALUES ($1, $2, $3, $4)",
        [
            (account_id, "pet_card", ids["pet"], "Protect this pet card"),
            (account_id, "avoid_card", ids["ramp_a"], "Never suggest this card"),
            (account_id, "avoid_archetype", None, "ramp"),
            (account_id, "general", None, "Avoid green cards and favor old favorites"),
            (account_id, "feedback_boosting", None, "enabled"),
            (account_id, "user_profile_boosting", None, "enabled"),
        ],
    )
    await pool.execute(
        """
        INSERT INTO account_ranking_weights
            (account_id, semantic, synergy, popularity, personal, deck_inclusion,
             moxfield_inclusion, trusted_quota)
        VALUES ($1, 99, 98, 97, 96, 95, 94, 0)
        """,
        account_id,
    )
    await pool.executemany(
        "INSERT INTO deck_feedback (deck_id, card_id, feedback, reject_count, reason) "
        "VALUES ($1, $2, $3, $4, $5)",
        [
            (deck_id, ids["ramp_a"], "up", 0, "legacy upvote"),
            (deck_id, ids["ramp_b"], "down", 0, "legacy downvote"),
            (other_deck, ids["garden"], "reject", 9, "legacy reject"),
        ],
    )
    await pool.executemany(
        "INSERT INTO deck_coach_memory (deck_id, account_id, notes) VALUES ($1, $2, $3)",
        [
            (deck_id, account_id, "Remember all personalization"),
            (other_deck, account_id, "Cross-deck taste"),
        ],
    )


async def test_real_recommendation_outcomes_ignore_seeded_legacy_tastes(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Builder, New Cards, and Discover retain ordered source/deck outcomes after legacy seeds."""
    ids = await _seed_retrieval_state(db_pool)
    deck_id = UUID(await create_test_deck(client, name="Legacy-insensitive deck"))
    await db_pool.executemany(
        "INSERT INTO deck_cards (deck_id, card_id) VALUES ($1, $2)",
        [
            (deck_id, ids["doubling_season"]),
            (deck_id, ids["pet"]),
            (deck_id, ids["plains"]),
        ],
    )
    await _publish_sources(db_pool, {ids["ramp_a"], ids["ramp_b"], ids["garden"]})
    account = await db_pool.fetchrow(
        "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
    )
    assert account is not None
    owner = discover_repository.Owner(account["id"], account["email"])
    before = await _outcomes(client, db_pool, deck_id, owner, ids["doubling_season"])

    ramp_a_scryfall = str(await _scryfall(db_pool, ids["ramp_a"]))
    ramp_b_scryfall = str(await _scryfall(db_pool, ids["ramp_b"]))
    garden_scryfall = str(await _scryfall(db_pool, ids["garden"]))
    pet_scryfall = str(await _scryfall(db_pool, ids["pet"]))
    reprint_scryfall = str(await _scryfall(db_pool, ids["reprint"]))
    assert ramp_a_scryfall in before["build"]
    assert "Tags" in before["build_sources"][ramp_a_scryfall]
    assert reprint_scryfall not in before["build"]
    assert ramp_a_scryfall in before["freeform"]
    assert garden_scryfall in before["mana"]
    assert ramp_b_scryfall in before["swap"]
    assert str(await _oracle(db_pool, ids["ramp_a"])) in before["new_cards"]
    assert (str(await _oracle(db_pool, ids["ramp_a"])), False) in before["discover"]
    assert (pet_scryfall, False) in before["fit"]
    excluded = await client.post(
        f"/api/v1/decks/{deck_id}/build", json={"stage": "ramp", "exclude": ["Seeded Ramp A"]}
    )
    assert ramp_a_scryfall not in _suggestion_ids(excluded.json()["data"]["suggestions"])

    await _seed_legacy_state(client, db_pool, deck_id, owner.account_id, ids)
    after = await _outcomes(client, db_pool, deck_id, owner, ids["doubling_season"])

    assert after == before

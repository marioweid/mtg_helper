"""Behavior tests for collection-aware assistant card search."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.models.ai import CardSearchHit
from mtg_helper.models.decks import CommanderCardSummary, DeckDetailResponse
from mtg_helper.services.mtg_assistant import (
    AssistantDeps,
    _attach_owned_quantities,
    _owned_card_ids,
)
from mtg_helper.services.mtg_card_search import (
    AssistantCardSearchInput,
    CardEvidenceSource,
    CardSearchCandidate,
    CardSearchResult,
    search_cards,
)

DOUBLING_SEASON_SCRYFALL_ID = UUID("1d7b8d2c-36f5-40e7-91de-9c8c1b44da67")
SOL_RING_SCRYFALL_ID = UUID("3d7b8d2c-36f5-40e7-91de-9c8c1b44da67")


async def _seed_account_and_collection(pool: asyncpg.Pool) -> tuple[str, str]:
    async with pool.acquire() as conn:
        account_id = await conn.fetchval(
            "INSERT INTO accounts (display_name, email) VALUES ('Coll User', 'coll@test.local') "
            "RETURNING id"
        )
        collection_id = await conn.fetchval(
            "INSERT INTO collections (account_id, name) VALUES ($1, 'Main') RETURNING id",
            account_id,
        )
    return str(account_id), str(collection_id)


async def _add_card_to_collection(pool: asyncpg.Pool, collection_id: str, scryfall_id: str) -> None:
    async with pool.acquire() as conn:
        card_id = await conn.fetchval("SELECT id FROM cards WHERE scryfall_id = $1", scryfall_id)
        await conn.execute(
            """
            INSERT INTO collection_cards (collection_id, card_id, set_code, collector_number)
            VALUES ($1, $2, 'lea', 'x')
            """,
            collection_id,
            card_id,
        )


def _deck() -> DeckDetailResponse:
    now = datetime.now(UTC)
    commander_id = uuid4()
    return DeckDetailResponse(
        id=uuid4(),
        name="Coll Deck",
        description=None,
        bracket=3,
        stage="complete",
        commander_id=commander_id,
        partner_id=None,
        commander_color_identity=["G", "W"],
        commander_card=CommanderCardSummary(
            id=commander_id,
            name="Hazel of the Rootbloom",
            color_identity=["G", "W"],
        ),
        owner_email="coll@test.local",
        created_at=now,
        updated_at=now,
        cards=[],
    )


async def test_owned_card_ids_resolves_account_collections(db_pool: asyncpg.Pool) -> None:
    account_id, collection_id = await _seed_account_and_collection(db_pool)
    await _add_card_to_collection(db_pool, collection_id, SOL_RING_SCRYFALL_ID)

    deps = AssistantDeps(pool=db_pool, deck=_deck(), account_id=uuid4())
    deps.account_id = account_id  # ensure the seeded uuid is used

    owned = await _owned_card_ids(deps)

    assert owned  # at least the Sol Ring canonical card is owned
    assert len(owned) >= 1


async def test_owned_card_ids_returns_empty_without_account(db_pool: asyncpg.Pool) -> None:
    deps = AssistantDeps(pool=db_pool, deck=_deck(), account_id=None)

    owned = await _owned_card_ids(deps)

    assert owned == frozenset()


async def test_attach_owned_quantities_enriches_candidates(db_pool: asyncpg.Pool) -> None:
    account_id, collection_id = await _seed_account_and_collection(db_pool)
    await _add_card_to_collection(db_pool, collection_id, SOL_RING_SCRYFALL_ID)
    result = CardSearchResult(
        evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
        candidates=[
            CardSearchCandidate(
                card=CardSearchHit(scryfall_id=SOL_RING_SCRYFALL_ID, name="Sol Ring"),
                evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
            ),
            CardSearchCandidate(
                card=CardSearchHit(scryfall_id=DOUBLING_SEASON_SCRYFALL_ID, name="Doubling Season"),
                evidence_source=CardEvidenceSource.GLOBAL_SEARCH,
            ),
        ],
    )
    deps = AssistantDeps(pool=db_pool, deck=_deck(), account_id=uuid4())
    deps.account_id = account_id

    await _attach_owned_quantities(deps, result)

    assert result.candidates[0].owned_quantity >= 1
    assert result.candidates[1].owned_quantity == 0


async def test_collection_only_search_restricts_via_tool_path(
    db_pool: asyncpg.Pool,
) -> None:
    """End-to-end: account collections drive a collection-only find_cards result."""
    account_id, collection_id = await _seed_account_and_collection(db_pool)
    await _add_card_to_collection(db_pool, collection_id, SOL_RING_SCRYFALL_ID)
    deps = AssistantDeps(pool=db_pool, deck=_deck(), account_id=account_id)

    owned = await _owned_card_ids(deps)
    result = await search_cards(
        db_pool,
        deps.deck,
        AssistantCardSearchInput(collection_only=True),
        owned_card_ids=owned,
    )

    names = {candidate.card.name for candidate in result.candidates}
    assert names  # non-empty
    assert "Sol Ring" in names

"""Scryfall tag-match route regression seam."""

from uuid import UUID

import pytest

from mtg_helper.services.new_cards.repository import Owner
from mtg_helper.services.new_cards.service import NewCardsService
from tests.conftest import create_test_deck

pytestmark = pytest.mark.asyncio


async def test_ac01_missing_sources_are_not_reported_as_no_matches(client, db_pool) -> None:
    deck_id = UUID(await create_test_deck(client))
    account = await db_pool.fetchrow(
        "SELECT id, email FROM accounts WHERE email = $1", "default@test.local"
    )
    assert account is not None
    result = await NewCardsService(db_pool).view(Owner(account["id"], account["email"]), deck_id)
    assert result.status == "unavailable"
    assert result.matches == []
    assert result.error is not None

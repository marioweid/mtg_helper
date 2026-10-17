"""Recommendation paths rely on deck state and source evidence only."""

import inspect
from uuid import uuid4

import pytest

from mtg_helper.services import ai_service, retrieval_service
from mtg_helper.services.recommendations import repository

pytestmark = pytest.mark.no_db


def test_retrieval_and_build_interfaces_have_no_personalization_inputs() -> None:
    """Legacy records cannot affect results when no retrieval input accepts them."""
    retrieval_parameters = inspect.signature(retrieval_service.retrieve_candidates).parameters
    build_source = inspect.getsource(ai_service)

    assert {"feedback_weights", "user_profile", "ranking_weights"}.isdisjoint(retrieval_parameters)
    assert "preference_service" not in build_source
    assert "profile_service" not in build_source
    assert "ranking_weight_service" not in build_source


class _Connection:
    async def fetch(self, query: str, *_args: object) -> list[object]:
        self.query = query
        return []


async def test_discover_exclusions_ignore_account_avoid_records() -> None:
    """Discover retains physical/planned exclusions without consulting preferences."""
    conn = _Connection()
    owner = repository.Owner(account_id=uuid4(), email="owner@example.com")

    assert await repository.exclusions(conn, owner, uuid4()) == set()
    assert "preferences" not in conn.query
    assert "deck_cards" in conn.query
    assert "deck_card_plans" in conn.query

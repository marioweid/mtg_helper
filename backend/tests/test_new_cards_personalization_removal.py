"""New Cards context excludes inactive personalization data."""

import inspect

import pytest

from mtg_helper.services.new_cards import repository

pytestmark = pytest.mark.no_db


def test_context_and_candidate_queries_do_not_reference_saved_tastes() -> None:
    """Saved notes and preferences cannot affect fresh advice or cache identity."""
    context_source = inspect.getsource(repository._context)
    candidate_source = inspect.getsource(repository._candidates)

    assert "preferences" not in context_source
    assert "deck_coach_memory" not in context_source
    assert "preferences" not in candidate_source
    assert "deck_coach_memory" not in candidate_source

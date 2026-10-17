"""Legacy personalization storage remains available for historical retention."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db


def test_schema_retains_inactive_personalization_tables() -> None:
    """Feature retirement is non-destructive: the idempotent schema keeps old rows."""
    schema = (Path(__file__).parents[1] / "src/mtg_helper/sql/schema.sql").read_text()

    for table in (
        "preferences",
        "account_ranking_weights",
        "deck_feedback",
        "deck_coach_memory",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema

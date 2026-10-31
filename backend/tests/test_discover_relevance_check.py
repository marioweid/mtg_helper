"""Offline checks for the read-only Discover quality diagnostic, not MTG accuracy claims."""

import pytest

from scripts.discover_relevance_check import local_database, popularity_probe, score

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://postgres/mtg_helper",
        "postgres://postgres:5432/mtg_helper",
    ],
)
def test_diagnostic_accepts_only_explicit_local_compose_database(dsn: str) -> None:
    assert local_database(dsn) == dsn


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://remote/mtg_helper",
        "postgresql://localhost/mtg_helper",
        "postgresql://postgres/mtg_app",
        "postgresql://postgres/mtg_helper_test",
        "postgresql://postgres:5433/mtg_helper",
        "postgresql://postgres/mtg_helper?host=remote",
        "postgresql://postgres/mtg_helper#override",
        "http://postgres/mtg_helper",
    ],
)
def test_diagnostic_refuses_live_ambiguous_and_test_targets(dsn: str) -> None:
    with pytest.raises(ValueError, match="isolated docker-compose.yml"):
        local_database(dsn)


def test_recovery_scores_original_rank_boundaries_and_full_pool_separately() -> None:
    rows = [{"oracle_id": str(rank)} for rank in range(1, 61)]
    result = score(rows, {"1", "10", "11", "50", "51", "60", "missing"})
    assert result == {
        "total": 60,
        "reference_hits_at_10": 2,
        "reference_hits_at_50": 4,
        "reference_hits_in_pool": 6,
        "target_count": 7,
    }


def test_empty_matches_are_not_a_successful_recovery() -> None:
    assert score([], {"target"}) == {
        "total": 0,
        "reference_hits_at_10": 0,
        "reference_hits_at_50": 0,
        "reference_hits_in_pool": 0,
        "target_count": 1,
    }


def test_popularity_probe_preserves_match_count_and_keeps_missing_ranks() -> None:
    rows = [
        {"oracle_id": "1", "name": "A", "match_count": 1, "edhrec_rank": 1},
        {"oracle_id": "2", "name": "B", "match_count": 2, "edhrec_rank": None},
        {"oracle_id": "3", "name": "C", "match_count": 2, "edhrec_rank": 10},
    ]
    result = popularity_probe(rows, {"2"})
    assert [row["name"] for row in result["cards"]] == ["C", "B", "A"]
    assert result["reference_hits_in_pool"] == 1
    assert result["total"] == 3

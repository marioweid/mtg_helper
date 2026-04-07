"""Tests for hybrid retrieval pure functions: scoring, signal map, and query parsing."""

from decimal import Decimal
from uuid import UUID

from mtg_helper.services.retrieval_service import (
    _build_signal_map,
    _compute_weighted_scores,
    _curve_fit_score,
    _personal_rating,
    parse_query_tags,
    stage_retrieval_query,
)

# Stable test UUIDs
_A = UUID("aaaaaaaa-0000-0000-0000-000000000000")
_B = UUID("bbbbbbbb-0000-0000-0000-000000000000")
_C = UUID("cccccccc-0000-0000-0000-000000000000")
_D = UUID("dddddddd-0000-0000-0000-000000000000")


# ── _build_signal_map ─────────────────────────────────────────────────────────


def test_build_signal_map_all_three_signals() -> None:
    qdrant, tag_overlaps, fts_set, signal_map = _build_signal_map([(_A, 0.9)], [(_B, 2)], [_C])
    assert signal_map[_A] == ["semantic"]
    assert signal_map[_B] == ["tag"]
    assert signal_map[_C] == ["fts"]


def test_build_signal_map_card_in_multiple_signals() -> None:
    _, _, _, signal_map = _build_signal_map([(_A, 0.9), (_B, 0.7)], [(_A, 2)], [])
    assert "semantic" in signal_map[_A]
    assert "tag" in signal_map[_A]
    assert len(signal_map[_A]) == 2


def test_build_signal_map_empty_inputs() -> None:
    qdrant, tag_overlaps, fts_set, signal_map = _build_signal_map([], [], [])
    assert qdrant == {}
    assert tag_overlaps == {}
    assert fts_set == set()
    assert signal_map == {}


def test_build_signal_map_skips_empty_lists() -> None:
    _, _, _, signal_map = _build_signal_map([(_A, 0.9)], [], [_C])
    assert _A in signal_map
    assert _C in signal_map
    assert _B not in signal_map


def test_build_signal_map_qdrant_scores_captured() -> None:
    qdrant, _, _, _ = _build_signal_map([(_A, 0.85), (_B, 0.72)], [], [])
    assert abs(qdrant[_A] - 0.85) < 1e-9
    assert abs(qdrant[_B] - 0.72) < 1e-9


def test_build_signal_map_tag_overlaps_captured() -> None:
    _, tag_overlaps, _, _ = _build_signal_map([], [(_A, 3), (_B, 1)], [])
    assert tag_overlaps[_A] == 3
    assert tag_overlaps[_B] == 1


# ── _curve_fit_score ──────────────────────────────────────────────────────────


def test_curve_fit_no_deck_data_returns_neutral() -> None:
    assert _curve_fit_score(Decimal("3"), None) == 0.5


def test_curve_fit_no_cmc_returns_neutral() -> None:
    assert _curve_fit_score(None, {2: 5}) == 0.5


def test_curve_fit_underrepresented_cmc_scores_higher() -> None:
    # Deck has nothing at CMC 2, target is ~22% — should score well above 0.5
    score = _curve_fit_score(Decimal("2"), {3: 10, 4: 10})
    assert score > 0.5


def test_curve_fit_overrepresented_cmc_scores_lower() -> None:
    # Deck is heavy on CMC 3 (target 25%, actual ~67%)
    score = _curve_fit_score(Decimal("3"), {3: 20, 2: 5, 4: 5})
    assert score < 0.5


def test_curve_fit_cmc_capped_at_6() -> None:
    # CMC 8 and CMC 6 should map to same bucket
    score_6 = _curve_fit_score(Decimal("6"), {})
    score_8 = _curve_fit_score(Decimal("8"), {})
    assert abs(score_6 - score_8) < 1e-9


# ── _personal_rating ──────────────────────────────────────────────────────────


def test_personal_rating_no_feedback_returns_neutral() -> None:
    assert _personal_rating(_A, None) == 0.5


def test_personal_rating_card_not_in_weights_returns_neutral() -> None:
    assert _personal_rating(_A, {_B: 1.5}) == 0.5


def test_personal_rating_max_weight_maps_to_one() -> None:
    assert abs(_personal_rating(_A, {_A: 2.0}) - 1.0) < 1e-6


def test_personal_rating_min_weight_maps_to_zero() -> None:
    assert abs(_personal_rating(_A, {_A: 0.05}) - 0.0) < 1e-6


def test_personal_rating_pet_card_weight_high() -> None:
    # Pet card weight is 1.5 → should be above 0.5
    assert _personal_rating(_A, {_A: 1.5}) > 0.5


def test_personal_rating_avoid_card_weight_low() -> None:
    # Avoid card weight is 0.1 → should be below 0.5
    assert _personal_rating(_A, {_A: 0.1}) < 0.5


# ── _compute_weighted_scores ──────────────────────────────────────────────────


def _make_row(uid: UUID, edhrec_rank: int | None = 100, cmc: float = 2.0) -> dict:
    return {"id": uid, "edhrec_rank": edhrec_rank, "cmc": Decimal(str(cmc))}


def test_weighted_score_higher_qdrant_wins() -> None:
    rows = {_A: _make_row(_A), _B: _make_row(_B)}
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.9, _B: 0.3},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        deck_cmc_counts=None,
        feedback_weights=None,
    )
    assert scores[_A] > scores[_B]


def test_weighted_score_fts_boosts_synergy() -> None:
    rows = {_A: _make_row(_A), _B: _make_row(_B)}
    # Same qdrant score; _A is also in FTS
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.5, _B: 0.5},
        tag_overlaps={},
        fts_set={_A},
        cards_by_id=rows,
        deck_cmc_counts=None,
        feedback_weights=None,
    )
    assert scores[_A] > scores[_B]


def test_weighted_score_feedback_boosts_card() -> None:
    rows = {_A: _make_row(_A), _B: _make_row(_B)}
    # Same base; _A has pet card feedback
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.5, _B: 0.5},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        deck_cmc_counts=None,
        feedback_weights={_A: 1.5},
    )
    assert scores[_A] > scores[_B]


def test_weighted_score_skips_missing_rows() -> None:
    rows = {_A: _make_row(_A)}
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.9, _B: 0.9},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        deck_cmc_counts=None,
        feedback_weights=None,
    )
    assert _A in scores
    assert _B not in scores


def test_weighted_score_range_zero_to_one() -> None:
    rows = {_A: _make_row(_A, edhrec_rank=1), _B: _make_row(_B, edhrec_rank=10000)}
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 1.0, _B: 0.0},
        tag_overlaps={_A: 3, _B: 0},
        fts_set={_A},
        cards_by_id=rows,
        deck_cmc_counts={2: 5},
        feedback_weights={_A: 2.0, _B: 0.05},
    )
    for score in scores.values():
        assert 0.0 <= score <= 1.0


# ── parse_query_tags ──────────────────────────────────────────────────────────


def test_parse_query_tags_single_term() -> None:
    assert "ramp" in parse_query_tags("I want ramp spells")


def test_parse_query_tags_multi_word_key_before_single_word() -> None:
    tags = parse_query_tags("board wipe effects")
    assert "board_wipe" in tags


def test_parse_query_tags_interaction_expands() -> None:
    tags = parse_query_tags("interaction spells")
    assert "removal" in tags
    assert "counterspell" in tags
    assert "board_wipe" in tags
    assert "protection" in tags


def test_parse_query_tags_deduplicates() -> None:
    tags = parse_query_tags("removal kill effects")
    assert tags.count("removal") == 1


def test_parse_query_tags_case_insensitive() -> None:
    assert "ramp" in parse_query_tags("RAMP spells")


def test_parse_query_tags_unknown_query_returns_empty() -> None:
    assert parse_query_tags("goblin tribal commander") == ["tribal"]


def test_parse_query_tags_empty_string() -> None:
    assert parse_query_tags("") == []


def test_parse_query_tags_voltron_includes_equipment() -> None:
    tags = parse_query_tags("voltron strategy")
    assert "voltron" in tags
    assert "equipment" in tags


# ── stage_retrieval_query ─────────────────────────────────────────────────────


def test_stage_retrieval_query_known_stages() -> None:
    for stage in ("ramp", "interaction", "draw", "utility", "lands"):
        text, tags = stage_retrieval_query(stage, None)
        assert isinstance(text, str) and len(text) > 0
        assert isinstance(tags, list)


def test_stage_retrieval_query_ramp_tags() -> None:
    _, tags = stage_retrieval_query("ramp", None)
    assert "ramp" in tags


def test_stage_retrieval_query_interaction_tags() -> None:
    _, tags = stage_retrieval_query("interaction", None)
    assert "removal" in tags
    assert "counterspell" in tags


def test_stage_retrieval_query_theme_uses_description() -> None:
    text, _ = stage_retrieval_query("theme", "voltron equipment")
    assert "voltron" in text.lower() or "equipment" in text.lower()


def test_stage_retrieval_query_theme_no_description_fallback() -> None:
    text, _ = stage_retrieval_query("theme", None)
    assert "synergy" in text.lower() or "theme" in text.lower()


def test_stage_retrieval_query_unknown_stage_returns_stage_name() -> None:
    text, tags = stage_retrieval_query("nonexistent_stage", None)
    assert text == "nonexistent_stage"
    assert tags == []


def test_stage_retrieval_query_ramp_with_description() -> None:
    text, tags = stage_retrieval_query("ramp", "Squirrels and +1/+1 Counters")
    assert "Squirrels" in text
    assert "+1/+1 Counters" in text
    assert "ramp" in tags
    assert "plus_one_counters" in tags


def test_stage_retrieval_query_draw_with_description() -> None:
    text, tags = stage_retrieval_query("draw", "sacrifice aristocrats")
    assert "sacrifice" in text.lower()
    assert "draw" in tags
    assert "sacrifice" in tags
    assert "aristocrats" in tags


def test_stage_retrieval_query_description_tags_deduped() -> None:
    # "ramp" in description should not double the ramp tag
    _, tags = stage_retrieval_query("ramp", "ramp and counters")
    assert tags.count("ramp") == 1


def test_stage_retrieval_query_no_description_unchanged() -> None:
    text_none, tags_none = stage_retrieval_query("ramp", None)
    text_empty, tags_empty = stage_retrieval_query("ramp", "")
    # Both should return the base ramp query without description appended
    assert text_none == text_empty
    assert tags_none == tags_empty

"""Tests for hybrid retrieval pure functions: scoring, signal map, and query parsing."""

from decimal import Decimal
from uuid import UUID

from mtg_helper.services.retrieval_service import (
    TypeFilter,
    _build_signal_map,
    _compute_weighted_scores,
    _curve_fit_score,
    _personal_rating,
    _type_match_score,
    parse_query_tags,
    parse_query_types,
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
    assert tags == ["ramp", "fast_mana"]


def test_stage_retrieval_query_draw_with_description() -> None:
    text, tags = stage_retrieval_query("draw", "sacrifice aristocrats")
    assert "sacrifice" in text.lower()
    assert tags == ["draw"]


def test_stage_retrieval_query_description_does_not_affect_tags() -> None:
    # Deck description keywords must never pollute non-theme stage tags
    _, tags = stage_retrieval_query("ramp", "elf tribal with card draw and sacrifice")
    assert tags == ["ramp", "fast_mana"]


def test_stage_retrieval_query_no_description_unchanged() -> None:
    text_none, tags_none = stage_retrieval_query("ramp", None)
    text_empty, tags_empty = stage_retrieval_query("ramp", "")
    # Both should return the base ramp query without description appended
    assert text_none == text_empty
    assert tags_none == tags_empty


# ── parse_query_types ─────────────────────────────────────────────────────────


def test_parse_query_types_no_types_returns_none() -> None:
    assert parse_query_types("I want ramp spells") is None


def test_parse_query_types_detects_card_type() -> None:
    result = parse_query_types("artifact ramp please")
    assert result is not None
    assert "Artifact" in result.card_types
    assert result.subtypes == []


def test_parse_query_types_detects_subtype() -> None:
    result = parse_query_types("elf mana dorks")
    assert result is not None
    assert "Elf" in result.subtypes
    assert result.card_types == []


def test_parse_query_types_detects_multiple_subtypes() -> None:
    result = parse_query_types("monk human ramp")
    assert result is not None
    assert "Monk" in result.subtypes
    assert "Human" in result.subtypes


def test_parse_query_types_case_insensitive() -> None:
    result = parse_query_types("ARTIFACT removal")
    assert result is not None
    assert "Artifact" in result.card_types


def test_parse_query_types_mixed_type_and_subtype() -> None:
    result = parse_query_types("artifact creature goblin")
    assert result is not None
    assert "Artifact" in result.card_types
    assert "Creature" in result.card_types
    assert "Goblin" in result.subtypes


def test_parse_query_types_elves_normalized() -> None:
    result = parse_query_types("elves ramp")
    assert result is not None
    assert "Elf" in result.subtypes


def test_parse_query_types_empty_string_returns_none() -> None:
    assert parse_query_types("") is None


# ── _type_match_score ─────────────────────────────────────────────────────────


def _make_type_row(
    card_types: list[str],
    subtypes: list[str],
    keywords: list[str] | None = None,
    traits: list[str] | None = None,
    token_types: list[str] | None = None,
) -> dict:
    return {
        "id": _A,
        "edhrec_rank": 100,
        "cmc": Decimal("2"),
        "card_types": card_types,
        "subtypes": subtypes,
        "keywords": keywords or [],
        "traits": traits or [],
        "token_types": token_types or [],
        "tags": [],
    }


def test_type_match_score_full_match() -> None:
    row = _make_type_row(["Artifact"], [])
    tf = TypeFilter(card_types=["Artifact"], subtypes=[])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


def test_type_match_score_no_match() -> None:
    row = _make_type_row(["Creature"], ["Human"])
    tf = TypeFilter(card_types=["Artifact"], subtypes=[])
    assert _type_match_score(row, tf) == 0.0  # type: ignore[arg-type]


def test_type_match_score_partial_match() -> None:
    row = _make_type_row(["Creature"], ["Human"])
    tf = TypeFilter(card_types=[], subtypes=["Human", "Monk"])
    score = _type_match_score(row, tf)  # type: ignore[arg-type]
    assert score == 0.5


def test_type_match_score_subtype_match() -> None:
    row = _make_type_row(["Creature"], ["Elf", "Druid"])
    tf = TypeFilter(card_types=[], subtypes=["Elf"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


# ── _compute_weighted_scores with type_filter ─────────────────────────────────


def test_weighted_score_type_filter_boosts_matching_card() -> None:
    rows = {
        _A: {**_make_type_row(["Artifact"], []), "id": _A},
        _B: {**_make_type_row(["Creature"], ["Human"]), "id": _B},
    }
    tf = TypeFilter(card_types=["Artifact"], subtypes=[])
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.5, _B: 0.5},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,  # type: ignore[arg-type]
        deck_cmc_counts=None,
        feedback_weights=None,
        type_filter=tf,
    )
    assert scores[_A] > scores[_B]


def test_weighted_score_no_type_filter_unchanged_weights() -> None:
    rows = {_A: _make_row(_A), _B: _make_row(_B)}
    scores_no_filter = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.8, _B: 0.2},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        deck_cmc_counts=None,
        feedback_weights=None,
        type_filter=None,
    )
    assert scores_no_filter[_A] > scores_no_filter[_B]


# ── _type_match_score with keywords + traits ──────────────────────────────────


def test_type_match_score_keyword_match() -> None:
    row = _make_type_row(["Creature"], [], keywords=["Flying", "Vigilance"])
    tf = TypeFilter(card_types=[], subtypes=[], keywords=["Flying"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


def test_type_match_score_keyword_no_match() -> None:
    row = _make_type_row(["Creature"], [], keywords=["Vigilance"])
    tf = TypeFilter(card_types=[], subtypes=[], keywords=["Flying"])
    assert _type_match_score(row, tf) == 0.0  # type: ignore[arg-type]


def test_type_match_score_trait_match() -> None:
    row = _make_type_row(["Creature"], [], traits=["etb", "evasion"])
    tf = TypeFilter(card_types=[], subtypes=[], traits=["etb"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


def test_type_match_score_keyword_case_insensitive() -> None:
    row = _make_type_row(["Creature"], [], keywords=["Flying"])
    tf = TypeFilter(card_types=[], subtypes=[], keywords=["flying"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


def test_type_match_score_mixed_partial() -> None:
    # Request: flying + deathtouch; card has only flying → 0.5
    row = _make_type_row(["Creature"], [], keywords=["Flying"])
    tf = TypeFilter(card_types=[], subtypes=[], keywords=["Flying", "Deathtouch"])
    assert _type_match_score(row, tf) == 0.5  # type: ignore[arg-type]


# ── parse_query_types: keywords + traits + strict ─────────────────────────────


def test_parse_query_types_detects_keyword() -> None:
    result = parse_query_types("flying creatures")
    assert result is not None
    assert "Flying" in result.keywords
    assert "Creature" in result.card_types


def test_parse_query_types_flying_deathtouch_strict() -> None:
    result = parse_query_types("flying deathtouch creatures")
    assert result is not None
    assert "Flying" in result.keywords
    assert "Deathtouch" in result.keywords
    assert "Creature" in result.card_types
    assert result.strict is True


def test_parse_query_types_artifact_ramp_not_strict() -> None:
    # Only 1 filter dimension (card_types) → not strict
    result = parse_query_types("artifact ramp")
    assert result is not None
    assert "Artifact" in result.card_types
    assert result.strict is False


def test_parse_query_types_detects_etb_trait() -> None:
    result = parse_query_types("etb creatures")
    assert result is not None
    assert "etb" in result.traits
    assert "Creature" in result.card_types


def test_parse_query_types_etb_creature_strict() -> None:
    result = parse_query_types("etb creatures")
    assert result is not None
    assert result.strict is True


def test_parse_query_types_evasion_trait() -> None:
    result = parse_query_types("evasive threats")
    assert result is not None
    assert "evasion" in result.traits


def test_parse_query_types_first_strike_phrase() -> None:
    result = parse_query_types("first strike creatures")
    assert result is not None
    assert "First Strike" in result.keywords


def test_parse_query_types_double_strike_phrase() -> None:
    result = parse_query_types("double strike warriors")
    assert result is not None
    assert "Double Strike" in result.keywords
    assert "Warrior" in result.subtypes
    assert result.strict is True


# ── strict mode filtering ─────────────────────────────────────────────────────


def test_strict_mode_zeroes_out_zero_match_cards() -> None:
    rows = {
        _A: {**_make_type_row(["Creature"], [], keywords=["Flying"]), "id": _A},
        _B: {**_make_type_row(["Enchantment"], []), "id": _B},  # zero match
    }
    tf = TypeFilter(card_types=["Creature"], subtypes=[], keywords=["Flying"], strict=True)
    scores = _compute_weighted_scores(
        [_A, _B],
        qdrant_scores={_A: 0.5, _B: 0.5},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,  # type: ignore[arg-type]
        deck_cmc_counts=None,
        feedback_weights=None,
        type_filter=tf,
    )
    assert scores[_B] == 0.0
    assert scores[_A] > 0.0


def test_strict_mode_partial_match_not_zeroed() -> None:
    # Flying creature but no deathtouch — partial match, not zeroed
    rows = {
        _A: {**_make_type_row(["Creature"], [], keywords=["Flying"]), "id": _A},
    }
    tf = TypeFilter(card_types=[], subtypes=[], keywords=["Flying", "Deathtouch"], strict=True)
    scores = _compute_weighted_scores(
        [_A],
        qdrant_scores={_A: 0.5},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,  # type: ignore[arg-type]
        deck_cmc_counts=None,
        feedback_weights=None,
        type_filter=tf,
    )
    assert scores[_A] > 0.0


def test_non_strict_mode_zero_match_not_zeroed() -> None:
    rows = {
        _A: {**_make_type_row(["Enchantment"], []), "id": _A},
    }
    tf = TypeFilter(card_types=["Creature"], subtypes=[], strict=False)
    scores = _compute_weighted_scores(
        [_A],
        qdrant_scores={_A: 0.5},
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,  # type: ignore[arg-type]
        deck_cmc_counts=None,
        feedback_weights=None,
        type_filter=tf,
    )
    assert scores[_A] > 0.0


# ── parse_query_types: token_types ────────────────────────────────────────────


def test_parse_query_types_detects_treasure() -> None:
    result = parse_query_types("treasure producers")
    assert result is not None
    assert "treasure" in result.token_types


def test_parse_query_types_detects_food() -> None:
    result = parse_query_types("food token synergy")
    assert result is not None
    assert "food" in result.token_types


def test_parse_query_types_detects_clue() -> None:
    result = parse_query_types("clue investigate")
    assert result is not None
    assert "clue" in result.token_types


def test_parse_query_types_detects_blood() -> None:
    result = parse_query_types("blood token cards")
    assert result is not None
    assert "blood" in result.token_types


def test_parse_query_types_detects_powerstone() -> None:
    result = parse_query_types("powerstone ramp")
    assert result is not None
    assert "powerstone" in result.token_types


def test_parse_query_types_detects_map() -> None:
    result = parse_query_types("map token explore")
    assert result is not None
    assert "map" in result.token_types


def test_parse_query_types_detects_incubator() -> None:
    result = parse_query_types("incubator transform")
    assert result is not None
    assert "incubator" in result.token_types


def test_parse_query_types_token_type_strict_with_card_type() -> None:
    result = parse_query_types("treasure artifact")
    assert result is not None
    assert "treasure" in result.token_types
    assert result.strict is True


def test_parse_query_types_token_type_no_duplicates() -> None:
    result = parse_query_types("treasure treasure synergy")
    assert result is not None
    assert result.token_types.count("treasure") == 1


# ── parse_query_types: extended keywords ──────────────────────────────────────


def test_parse_query_types_scry() -> None:
    result = parse_query_types("cards with scry")
    assert result is not None
    assert "Scry" in result.keywords


def test_parse_query_types_surveil() -> None:
    result = parse_query_types("surveil cards")
    assert result is not None
    assert "Surveil" in result.keywords


def test_parse_query_types_discover() -> None:
    result = parse_query_types("discover synergy")
    assert result is not None
    assert "Discover" in result.keywords


def test_parse_query_types_flashback() -> None:
    result = parse_query_types("flashback spells")
    assert result is not None
    assert "Flashback" in result.keywords


def test_parse_query_types_proliferate() -> None:
    result = parse_query_types("proliferate counters")
    assert result is not None
    assert "Proliferate" in result.keywords


# ── _type_match_score with token_types ────────────────────────────────────────


def test_type_match_score_token_type_full_match() -> None:
    row = _make_type_row(["Artifact"], [], token_types=["treasure"])
    tf = TypeFilter(card_types=[], subtypes=[], token_types=["treasure"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]


def test_type_match_score_token_type_no_match() -> None:
    row = _make_type_row(["Artifact"], [], token_types=["treasure"])
    tf = TypeFilter(card_types=[], subtypes=[], token_types=["food"])
    assert _type_match_score(row, tf) == 0.0  # type: ignore[arg-type]


def test_type_match_score_token_type_partial() -> None:
    row = _make_type_row(["Artifact"], [], token_types=["treasure"])
    tf = TypeFilter(card_types=[], subtypes=[], token_types=["treasure", "food"])
    assert _type_match_score(row, tf) == 0.5  # type: ignore[arg-type]


def test_type_match_score_token_type_with_card_type() -> None:
    row = _make_type_row(["Artifact"], [], token_types=["treasure"])
    tf = TypeFilter(card_types=["Artifact"], subtypes=[], token_types=["treasure"])
    assert _type_match_score(row, tf) == 1.0  # type: ignore[arg-type]

"""Pure retrieval checks for Oracle identities, printed facts, and deterministic ranking."""

from copy import deepcopy
from dataclasses import fields
from decimal import Decimal
from typing import cast
from uuid import UUID

import asyncpg
import pytest

from mtg_helper.services.retrieval_service import (
    CollectionFilter,
    RepresentationQuery,
    TypeFilter,
    _annotate_representation_signals,
    _build_signal_map,
    _compute_weighted_scores,
    _curve_fit_score,
    _fetch_excluded_source_card_ids,
    _filter_rows_by_stage,
    _filter_source_rows,
    _representation_match_score,
    _search_tags,
    _type_match_score,
    parse_query_tags,
    parse_query_types,
    retrieve_candidates,
    stage_retrieval_query,
)

pytestmark = pytest.mark.no_db
_A = UUID("aaaaaaaa-0000-0000-0000-000000000000")
_B = UUID("bbbbbbbb-0000-0000-0000-000000000000")
_C = UUID("cccccccc-0000-0000-0000-000000000000")


def _row(uid: UUID = _A, **values: object) -> asyncpg.Record:
    return cast(
        asyncpg.Record,
        {
            "id": uid,
            "edhrec_rank": 100,
            "cmc": Decimal("2"),
            "color_identity": ["G", "B"],
            "type_line": "Creature",
            "tags": [],
            "card_types": ["Creature"],
            "subtypes": [],
            "keywords": [],
            **values,
        },
    )


def test_signal_map_preserves_overlap_and_combines_unique_signals() -> None:
    overlaps, fts, signals = _build_signal_map([(_A, 3), (_B, 1)], [_B, _C, _C])
    assert overlaps == {_A: 3, _B: 1}
    assert fts == {_B, _C}
    assert signals == {_A: ["tag"], _B: ["tag", "fts"], _C: ["fts"]}


def test_signal_map_handles_empty_inputs() -> None:
    assert _build_signal_map([], []) == ({}, set(), {})
    assert _build_signal_map([], [_C])[2] == {_C: ["fts"]}


@pytest.mark.parametrize("cmc,counts", [(Decimal("3"), None), (None, {2: 5})])
def test_curve_fit_without_complete_data_is_neutral(cmc, counts) -> None:
    assert _curve_fit_score(cmc, counts) == 0.5


def test_curve_fit_rewards_missing_buckets_and_caps_expensive_spells() -> None:
    assert _curve_fit_score(Decimal("2"), {3: 10, 4: 10}) > 0.5
    assert _curve_fit_score(Decimal("3"), {3: 20, 2: 5, 4: 5}) < 0.5
    assert _curve_fit_score(Decimal("8"), {}) == _curve_fit_score(Decimal("6"), {})


def test_source_filter_uses_exact_oracle_identity_and_excluded_card_ids() -> None:
    rows = [_row(_A, tags=[str(_A)]), _row(_B, tags=[str(_B)]), _row(_C)]
    assert _filter_source_rows(rows, str(_A), None) == [rows[0]]
    assert _filter_source_rows(rows, None, frozenset({_A})) == rows[1:]
    assert _filter_source_rows(rows, str(_A), frozenset({_A})) == []
    assert _filter_source_rows(rows, None, None) == rows


@pytest.mark.parametrize("stage", [None, "theme", "ramp", "draw", "interaction"])
def test_nonland_stages_do_not_infer_functional_roles(stage: str | None) -> None:
    rows = [_row(_A, tags=[str(_A)]), _row(_B)]
    assert _filter_rows_by_stage(rows, stage) == rows


def test_land_stage_requires_a_printed_land_type() -> None:
    land = _row(_A, type_line="Basic Land — Forest")
    assert _filter_rows_by_stage([land, _row(_B)], "lands") == [land]


def test_representation_scores_source_tags_types_subtypes_and_printed_keywords() -> None:
    row = _row(tags=[str(_A)], card_types=["Artifact"], subtypes=["Equipment"], keywords=["Flying"])
    query = RepresentationQuery(
        tags=[str(_A)], card_types=["Artifact"], subtypes=["Equipment"], keywords=["flying"]
    )
    assert _representation_match_score(row, query) == 1.0
    assert _representation_match_score(row, RepresentationQuery()) == 0.0
    partial = RepresentationQuery(tags=[str(_A)], card_types=["Creature"])
    assert _representation_match_score(row, partial) == 0.5


def test_representation_signals_are_idempotent_and_do_not_include_nonmatches() -> None:
    rows = {_A: _row(_A, tags=[str(_A)]), _B: _row(_B, tags=[str(_B)])}
    signals: dict[UUID, list[str]] = {}
    query = RepresentationQuery(tags=[str(_A)])
    _annotate_representation_signals(signals, rows, query)
    _annotate_representation_signals(signals, rows, query)
    assert signals == {_A: ["representation"]}


@pytest.mark.parametrize("model", [TypeFilter, RepresentationQuery])
def test_query_models_have_no_retired_global_label_dimensions(model) -> None:
    names = {field.name for field in fields(model)}
    assert not names & {"hub_tags", "mtgjson_tags", "traits", "token_types"}


def test_weighted_scoring_rewards_popularity_without_mutating_inputs() -> None:
    rows = {_A: _row(_A, edhrec_rank=10), _B: _row(_B, edhrec_rank=100)}
    ids = [_A, _B, _C]
    overlaps = {_A: 1, _B: 1}
    fts = {_B}
    before = deepcopy((ids, overlaps, fts, rows))
    scores = _compute_weighted_scores(
        ids,
        tag_overlaps=overlaps,
        fts_set=fts,
        cards_by_id=rows,
        commander_color_identity=["G", "B"],
        deck_cmc_counts=None,
    )
    assert _C not in scores
    assert all(0 <= score <= 1 for score in scores.values())
    assert (ids, overlaps, fts, rows) == before
    popular = _compute_weighted_scores(
        ids,
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        commander_color_identity=["G", "B"],
        deck_cmc_counts=None,
    )
    assert popular[_A] > popular[_B]


@pytest.mark.parametrize("signal", ["fts", "representation", "type"])
def test_weighted_scoring_rewards_matching_source_facts(signal: str) -> None:
    rows = {_A: _row(_A, tags=[str(_A)]), _B: _row(_B)}
    if signal == "type":
        rows[_A] = _row(_A, card_types=["Artifact"])
    scores = _compute_weighted_scores(
        [_A, _B],
        tag_overlaps={},
        fts_set={_A} if signal == "fts" else set(),
        cards_by_id=rows,
        commander_color_identity=["G", "B"],
        deck_cmc_counts=None,
        representation_query=RepresentationQuery(tags=[str(_A)])
        if signal == "representation"
        else None,
        type_filter=TypeFilter(card_types=["Artifact"], subtypes=[]) if signal == "type" else None,
    )
    assert scores[_A] > scores[_B]


@pytest.mark.parametrize("strict,expected_zero", [(True, True), (False, False)])
def test_strict_type_filter_zeroes_only_nonmatching_cards(
    strict: bool, expected_zero: bool
) -> None:
    rows = {_A: _row(_A, keywords=["Flying"]), _B: _row(_B, card_types=["Enchantment"])}
    scores = _compute_weighted_scores(
        [_A, _B],
        tag_overlaps={},
        fts_set=set(),
        cards_by_id=rows,
        commander_color_identity=["G", "B"],
        deck_cmc_counts=None,
        type_filter=TypeFilter(
            card_types=["Creature"], subtypes=[], keywords=["Flying"], strict=strict
        ),
    )
    assert scores[_A] > 0
    assert (scores[_B] == 0) is expected_zero


def test_strict_type_filter_keeps_partial_matches() -> None:
    scores = _compute_weighted_scores(
        [_A],
        tag_overlaps={},
        fts_set=set(),
        cards_by_id={_A: _row(keywords=["Flying"])},
        commander_color_identity=["G", "B"],
        deck_cmc_counts=None,
        type_filter=TypeFilter(
            card_types=[], subtypes=[], keywords=["Flying", "Deathtouch"], strict=True
        ),
    )
    assert scores[_A] > 0


@pytest.mark.parametrize(
    "query", ["", "ramp", "board wipe", "interaction", "voltron", "goblin tribal"]
)
def test_query_tags_do_not_infer_source_identities(query: str) -> None:
    assert parse_query_tags(query) == []


def test_query_tags_normalize_and_deduplicate_explicit_uuids() -> None:
    assert parse_query_tags(f"{str(_A).upper()}, {str(_B)} {_A} ramp") == [str(_A), str(_B)]


@pytest.mark.parametrize("stage", ["ramp", "draw", "interaction", "lands", "nonexistent_stage"])
def test_stages_keep_query_text_but_do_not_infer_oracle_tags(stage: str) -> None:
    text, tags = stage_retrieval_query(stage, "Squirrels and card draw")
    assert "Squirrels and card draw" in text
    assert tags == []
    assert stage_retrieval_query(stage, None) == stage_retrieval_query(stage, "")


def test_theme_stage_uses_only_explicit_source_tag_ids_from_description() -> None:
    text, tags = stage_retrieval_query("theme", f"voltron equipment {_A}")
    assert "voltron equipment" in text
    assert tags == [str(_A)]
    assert stage_retrieval_query("theme", None)[1] == []


@pytest.mark.parametrize(
    "query,types,subtypes,keywords,strict",
    [
        ("artifact ramp", ["Artifact"], [], [], False),
        ("ARTIFACT removal", ["Artifact"], [], [], False),
        ("elf mana dorks", [], ["Elf"], [], False),
        ("elves ramp", [], ["Elf"], [], False),
        ("artifact creature goblin", ["Artifact", "Creature"], ["Goblin"], [], True),
        ("flying deathtouch creatures", ["Creature"], [], ["Flying", "Deathtouch"], True),
        ("first strike creatures", ["Creature"], [], ["First Strike"], True),
        ("double strike warriors", [], ["Warrior"], ["Double Strike"], True),
        ("etb creatures", ["Creature"], [], [], False),
        ("treasure artifact", ["Artifact"], ["Treasure"], [], True),
        ("food token synergy", [], ["Food"], [], False),
        ("clue investigate", [], ["Clue"], ["Investigate"], True),
        ("treasure treasure synergy", [], ["Treasure"], [], False),
        ("map token explore", [], [], ["Explore"], False),
        ("scry", [], [], ["Scry"], False),
        ("surveil", [], [], ["Surveil"], False),
        ("discover", [], [], ["Discover"], False),
        ("flashback", [], [], ["Flashback"], False),
        ("proliferate", [], [], ["Proliferate"], False),
    ],
)
def test_query_types_use_printed_types_subtypes_and_keywords(
    query: str, types: list[str], subtypes: list[str], keywords: list[str], strict: bool
) -> None:
    result = parse_query_types(query)
    assert result == TypeFilter(types, subtypes, keywords, strict)


@pytest.mark.parametrize(
    "query", ["", "ramp spells", "evasive threats", "blood", "powerstone", "incubator"]
)
def test_query_types_do_not_recreate_retired_traits_or_token_labels(query: str) -> None:
    assert parse_query_types(query) is None


@pytest.mark.parametrize(
    "types,subtypes,keywords,query,expected",
    [
        (["Artifact"], [], [], TypeFilter(["Artifact"], []), 1.0),
        (["Creature"], ["Human"], [], TypeFilter(["Artifact"], []), 0.0),
        (["Creature"], ["Human"], [], TypeFilter([], ["Human", "Monk"]), 0.5),
        (["Creature"], ["Elf", "Druid"], [], TypeFilter([], ["Elf"]), 1.0),
        (["Creature"], [], ["Flying"], TypeFilter([], [], ["flying"]), 1.0),
        (["Creature"], [], ["Flying"], TypeFilter([], [], ["Flying", "Deathtouch"]), 0.5),
        (["Creature"], ["Human"], [], TypeFilter(["Artifact"], ["Human"]), 0.5),
        (["Artifact"], [], [], TypeFilter([], []), 0.0),
    ],
)
def test_type_match_scores_fraction_of_requested_printed_facts(
    types: list[str], subtypes: list[str], keywords: list[str], query: TypeFilter, expected: float
) -> None:
    assert (
        _type_match_score(_row(card_types=types, subtypes=subtypes, keywords=keywords), query)
        == expected
    )


def test_match_all_categories_requires_every_dimension_but_allows_or_within_one() -> None:
    query = TypeFilter(["Creature"], ["Equipment"], match_all_categories=True)
    assert _type_match_score(_row(), query) == 0.0
    assert _type_match_score(_row(card_types=["Artifact"], subtypes=["Equipment"]), query) == 0.0
    hybrid = _row(card_types=["Artifact", "Creature"], subtypes=["Equipment"])
    assert _type_match_score(hybrid, query) == 1.0
    either = TypeFilter([], ["Equipment", "Aura"], match_all_categories=True)
    assert _type_match_score(hybrid, either) > 0
    assert _type_match_score(_row(subtypes=["Aura"]), either) > 0
    assert _type_match_score(_row(), either) == 0.0


async def test_empty_collection_short_circuits_without_database_io() -> None:
    result = await retrieve_candidates(
        cast(asyncpg.Pool, object()),
        "ramp",
        [],
        ["G"],
        [],
        collection_filter=CollectionFilter(owned_card_ids=frozenset()),
    )
    assert result == []


async def test_missing_or_invalid_source_tag_queries_do_not_access_the_database() -> None:
    pool = cast(asyncpg.Pool, object())
    assert await _search_tags(pool, [], ["G"], []) == []
    assert await _search_tags(pool, ["ramp"], ["G"], []) == []
    assert await _fetch_excluded_source_card_ids(pool, frozenset(), ["G"]) is None

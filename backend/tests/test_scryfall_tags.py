"""Scryfall Oracle-tag parsing and hierarchy behavior, independent of a database."""

import gzip
import json
from copy import deepcopy
from uuid import UUID

import pytest

from mtg_helper.services import scryfall_tags
from mtg_helper.services.scryfall_tags import OracleTagCatalog, parse_tags

pytestmark = pytest.mark.no_db

PARENT = "00000000-0000-4000-8000-000000000001"
CHILD = "00000000-0000-4000-8000-000000000002"
GRANDCHILD = "00000000-0000-4000-8000-000000000003"
CARD = "00000000-0000-4000-8000-000000000010"
OTHER = "00000000-0000-4000-8000-000000000011"


def tag(identity: str, **updates: object) -> dict:
    """Build a source-shaped record rather than manually classify a card."""
    return {
        "object": "tag",
        "type": "oracle",
        "id": identity,
        "slug": f"source-{identity[-12:]}",
        "label": f"Source {identity[-12:]}",
        "uri": "https://tagger.scryfall.com/tags/card/example",
        "description": None,
        "aliases": [],
        "parent_ids": [],
        "child_ids": [],
        "taggings": [],
        **updates,
    }


def archive(rows: list[dict]) -> bytes:
    return gzip.compress(b"\n".join(json.dumps(row).encode() for row in rows), mtime=0)


def hierarchy() -> list[dict]:
    return [
        tag(PARENT, child_ids=[CHILD], aliases=["original-alias"]),
        tag(CHILD, parent_ids=[PARENT], child_ids=[GRANDCHILD]),
        tag(
            GRANDCHILD,
            parent_ids=[CHILD],
            description="Original source description",
            taggings=[{"oracle_id": CARD, "weight": "very_strong", "annotation": "note"}],
        ),
        tag(OTHER, taggings=[{"oracle_id": OTHER, "weight": "median"}]),
    ]


def test_parent_search_is_transitive_without_rewriting_direct_taggings() -> None:
    catalog = parse_tags(archive(hierarchy()))
    assert catalog.members(UUID(PARENT)) == {UUID(CARD)}
    assert catalog.members(UUID(CHILD)) == {UUID(CARD)}
    assert catalog.members(UUID(GRANDCHILD)) == {UUID(CARD)}
    assert catalog.tags[UUID(PARENT)].taggings == []
    direct = catalog.tags[UUID(GRANDCHILD)].taggings[0]
    assert direct.oracle_id == UUID(CARD)
    assert direct.weight == "very_strong"
    assert direct.annotation == "note"
    assert catalog.tags[UUID(PARENT)].aliases == ["original-alias"]
    assert catalog.tags[UUID(GRANDCHILD)].description == "Original source description"
    assert catalog.descendants[UUID(PARENT)] == {UUID(PARENT), UUID(CHILD), UUID(GRANDCHILD)}


def test_missing_tag_is_an_error_not_empty_success() -> None:
    catalog = parse_tags(archive(hierarchy()))
    with pytest.raises(ValueError, match="Unknown Scryfall tag"):
        catalog.members(UUID(CARD))


@pytest.mark.parametrize(
    "content",
    [b"not gzip", gzip.compress(b"not json"), gzip.compress(b"[]"), b""],
)
def test_malformed_archive_is_rejected(content: bytes) -> None:
    with pytest.raises(ValueError, match="Oracle-tag"):
        parse_tags(content)


def test_truncated_gzip_is_rejected_even_after_valid_rows() -> None:
    with pytest.raises(ValueError, match="Oracle-tag"):
        parse_tags(archive(hierarchy())[:-5])


@pytest.mark.parametrize(
    "updates",
    [
        {"id": "invalid"},
        {"type": "artwork"},
        {"object": "card"},
        {"slug": ""},
        {"taggings": [{"oracle_id": "invalid", "weight": "median"}]},
        {"taggings": [{"oracle_id": CARD, "weight": 1}]},
        {"parent_ids": ["invalid"]},
        {"aliases": "not a list"},
    ],
)
def test_bad_record_reports_its_line(updates: dict) -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_tags(archive([tag(PARENT), tag(CHILD, **updates)]))


def test_invalid_record_line_number_includes_blank_lines() -> None:
    content = gzip.compress(b"\n" + json.dumps(tag(PARENT, id="bad UUID")).encode())
    with pytest.raises(ValueError, match="line 2"):
        parse_tags(content)


def test_required_hierarchy_fields_cannot_silently_default_to_empty() -> None:
    row = tag(PARENT)
    del row["child_ids"]
    with pytest.raises(ValueError, match="line 1"):
        parse_tags(archive([row]))


@pytest.mark.parametrize("field", ["id", "slug"])
def test_duplicate_tag_identity_or_slug_is_rejected(field: str) -> None:
    rows = [tag(PARENT), tag(CHILD)]
    rows[1][field] = rows[0][field]
    with pytest.raises(ValueError, match="Duplicate Scryfall tag"):
        parse_tags(archive(rows))


def test_duplicate_direct_membership_is_rejected() -> None:
    membership = {"oracle_id": CARD, "weight": "median"}
    with pytest.raises(ValueError, match="Duplicate Oracle membership"):
        parse_tags(archive([tag(PARENT, taggings=[membership, membership])]))


@pytest.mark.parametrize("field", ["parent_ids", "child_ids"])
def test_missing_hierarchy_reference_is_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="Missing hierarchy reference"):
        parse_tags(archive([tag(PARENT, **{field: [CHILD]})]))


def test_nonreciprocal_hierarchy_is_rejected() -> None:
    with pytest.raises(ValueError, match="Nonreciprocal hierarchy"):
        parse_tags(archive([tag(PARENT, child_ids=[CHILD]), tag(CHILD)]))


def test_cycles_are_rejected() -> None:
    rows = [
        tag(PARENT, parent_ids=[CHILD], child_ids=[CHILD]),
        tag(CHILD, parent_ids=[PARENT], child_ids=[PARENT]),
    ]
    with pytest.raises(ValueError, match="Cycle in Scryfall tag hierarchy"):
        parse_tags(archive(rows))


def test_unknown_source_metadata_is_preserved() -> None:
    row = tag(PARENT, upstream_attribute={"value": "original"})
    catalog = parse_tags(archive([row]))
    assert catalog.records()[0]["upstream_attribute"] == {"value": "original"}


@pytest.mark.parametrize("limit", ["MAX_HIERARCHY_RELATIONS", "MAX_EXPANDED_MEMBERSHIPS"])
def test_pathological_graph_expansion_is_bounded(
    monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    monkeypatch.setattr(scryfall_tags, limit, 1)
    with pytest.raises(ValueError, match="expansion exceeds limits"):
        parse_tags(archive(hierarchy()))


def test_archive_byte_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    content = archive(hierarchy())
    monkeypatch.setattr(scryfall_tags, "MAX_TAG_BYTES", len(content) - 1)
    with pytest.raises(ValueError, match="archive exceeds"):
        parse_tags(content)


def test_decompressed_byte_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scryfall_tags, "MAX_TAG_BYTES", 1024)
    with pytest.raises(ValueError, match="JSONL exceeds size limits"):
        parse_tags(gzip.compress(b" " * 2000))


def test_line_byte_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scryfall_tags, "MAX_TAG_LINE_BYTES", 10)
    with pytest.raises(ValueError, match="JSONL exceeds size limits"):
        parse_tags(archive(hierarchy()))


def test_record_count_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scryfall_tags, "MAX_TAG_RECORDS", 1)
    with pytest.raises(ValueError, match="record count exceeds limits"):
        parse_tags(archive(hierarchy()))


def test_duplicate_hierarchy_edge_is_rejected() -> None:
    rows = hierarchy()
    rows[0]["child_ids"].append(CHILD)
    with pytest.raises(ValueError, match="Duplicate hierarchy reference"):
        parse_tags(archive(rows))


def test_records_are_stable_under_source_order_and_do_not_mutate_input() -> None:
    rows = hierarchy()
    original = deepcopy(rows)
    first = OracleTagCatalog.from_records(rows)
    second = OracleTagCatalog.from_records(list(reversed(rows)))
    assert first.records() == second.records()
    assert rows == original

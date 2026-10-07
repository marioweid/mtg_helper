"""Offline checks for the read-only New Cards data feasibility probe."""

import gzip
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from scripts.new_cards_data_spike import (
    download_export,
    first_paper_dates,
    iter_cards,
    paper_design,
    rules_text,
    window_state,
)

pytestmark = pytest.mark.no_db


def test_first_date_ignores_later_reprints_and_digital_history() -> None:
    base = {"oracle_id": "same", "layout": "normal", "games": ["paper"]}
    cards = [
        base | {"released_at": "2026-10-01", "reprint": True},
        base | {"released_at": "2026-08-01"},
        base | {"released_at": "2020-01-01", "games": ["arena"]},
        base | {"released_at": "2019-01-01", "security_stamp": "acorn"},
    ]
    dates, counts = first_paper_dates(iter(cards))
    assert dates == {"same": "2026-08-01"}
    assert counts["all_printings"] == 4
    assert counts["paper_printings"] == 2


@pytest.mark.parametrize(
    ("released", "expected"),
    [
        (None, "unknown"),
        ("2026-10-05", "upcoming"),
        ("2026-10-04", "recent"),
        ("2026-08-06", "recent"),
        ("2026-08-05", "expired"),
    ],
)
def test_expiry_boundary(released: str | None, expected: str) -> None:
    assert window_state(released, date(2026, 10, 4)) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"games": ["arena"]},
        {"oracle_id": None},
        {"layout": "token"},
        {"security_stamp": "acorn"},
        {"border_color": "silver"},
        {"set_type": "memorabilia"},
    ],
)
def test_paper_shape_exclusions(change: dict) -> None:
    assert not paper_design({"oracle_id": "x", "games": ["paper"]} | change)


def test_paper_shape_does_not_pretend_to_certify_legality() -> None:
    assert paper_design(
        {"oracle_id": "x", "games": ["paper"], "legalities": {"commander": "not_legal"}}
    )


def test_face_text_is_not_lost() -> None:
    card = {
        "card_faces": [
            {"name": "Front", "oracle_text": "Draw a card."},
            {"name": "Back", "oracle_text": "Add green mana."},
        ]
    }
    text = rules_text(card)
    assert "Front" in text and "Back" in text
    assert "Draw a card." in text and "Add green mana." in text
    assert rules_text({"oracle_text": "Normal rules"}) == "Normal rules"
    assert rules_text({}) == ""


def test_missing_date_is_reported_not_invented() -> None:
    dates, counts = first_paper_dates(iter([{"oracle_id": "x", "games": ["paper"]}]))
    assert dates == {}
    assert counts["paper_missing_release"] == 1


def test_gzip_jsonl_stream(tmp_path: Path) -> None:
    path = tmp_path / "cards.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write('\n{"object":"card","name":"Test"}\n')
    assert list(iter_cards(path)) == [{"object": "card", "name": "Test"}]


@pytest.mark.parametrize("value", [[], {"object": "set"}])
def test_invalid_archive_object_fails(tmp_path: Path, value: object) -> None:
    path = tmp_path / "bad.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(value))
    with pytest.raises(ValueError, match="line 1"):
        list(iter_cards(path))


def test_download_rejects_untrusted_host(tmp_path: Path) -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="non-Scryfall"):
        download_export(client, {"jsonl_download_uri": "https://example.com/card.gz"}, tmp_path)


def test_failed_download_does_not_replace_previous_archive(tmp_path: Path) -> None:
    path = tmp_path / "oracle_cards.jsonl.gz"
    path.write_bytes(b"previous")
    transport = httpx.MockTransport(lambda request: httpx.Response(429))
    entry = {"type": "oracle_cards", "jsonl_download_uri": "https://data.scryfall.io/test.gz"}
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        download_export(client, entry, tmp_path)
    assert path.read_bytes() == b"previous"

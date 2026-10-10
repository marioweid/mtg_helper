"""Artwork is optional, trusted-CDN presentation metadata, never model evidence."""

import pytest

from mtg_helper.services.recommendations.artwork import safe_uri

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    "uri",
    [
        None,
        "",
        "http://cards.scryfall.io/card.jpg",
        "javascript:alert(1)",
        "https://evil.example/card.jpg",
        "https://cards.scryfall.io.evil.example/card.jpg",
        "https://cards.scryfall.io@evil.example/card.jpg",
        "https://user@cards.scryfall.io/card.jpg",
        "https://cards.scryfall.io:123/card.jpg",
        "https://[malformed/card.jpg",
        "https://cards.scryfall.io/\\evil.example/card.jpg",
        "https://cards.scryfall.io/card\n.jpg",
    ],
)
def test_missing_or_unsafe_artwork_is_not_published(uri: str | None) -> None:
    assert safe_uri(uri) is None


def test_source_cdn_artwork_and_print_timestamp_are_preserved() -> None:
    uri = "https://cards.scryfall.io/normal/front/a/b/card.jpg?123"
    assert safe_uri(uri) == uri

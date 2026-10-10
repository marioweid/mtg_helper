"""Current-catalog artwork, kept outside immutable gameplay facts and provider inputs."""

from urllib.parse import urlsplit
from uuid import UUID

import asyncpg

from mtg_helper.models.recommendations import CandidateView


def safe_uri(uri: str | None) -> str | None:
    """Keep only HTTPS artwork on Scryfall's image CDN; malformed metadata stays absent."""
    if not uri or "\\" in uri or any(char.isspace() for char in uri):
        return None
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc != "cards.scryfall.io":
        return None
    return uri


async def attach(conn: asyncpg.Connection, candidates: list[CandidateView]) -> None:
    """Attach presentation-only images in one batch after the caller authorizes the view.

    Args:
        conn: Authorized request's database connection.
        candidates: Source/result projections to enrich without changing their facts.
    """
    if not candidates:
        return
    rows = await conn.fetch(
        "SELECT DISTINCT ON (oracle_id) oracle_id, image_uri FROM cards "
        "WHERE oracle_id = ANY($1::uuid[]) "
        "ORDER BY oracle_id, (image_uri IS NULL), id",
        [UUID(str(candidate.oracle_id)) for candidate in candidates],
    )
    images = {row["oracle_id"]: safe_uri(row["image_uri"]) for row in rows}
    for candidate in candidates:
        candidate.image_uri = images.get(candidate.oracle_id)

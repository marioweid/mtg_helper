"""One Scryfall bulk manifest and bounded downloads with retained source receipts."""

import json
from collections.abc import AsyncIterator
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from mtg_helper.config import settings

ExportKind = Literal["oracle_cards", "default_cards", "oracle_tags"]
EXPORT_KINDS: tuple[ExportKind, ...] = ("oracle_cards", "default_cards", "oracle_tags")
_MAX_MANIFEST_BYTES = 1024 * 1024


class BulkExport(BaseModel):
    """An upstream export receipt, including extra manifest fields for provenance."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    type: ExportKind
    updated_at: AwareDatetime
    jsonl_download_uri: str = Field(min_length=1)

    @field_validator("jsonl_download_uri")
    @classmethod
    def trusted_download(cls, value: str) -> str:
        """Allow only HTTPS Scryfall bulk hosts, with no credentials or alternate ports."""
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not (parsed.hostname or "").endswith(".scryfall.io")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.fragment
        ):
            raise ValueError("Scryfall returned an untrusted bulk download URL")
        return value


async def stream_export(client: httpx.AsyncClient, url: str, limit: int) -> AsyncIterator[bytes]:
    """Enforce raw transfer bounds before any HTTP decoding or file decompression.

    Args:
        client: Existing sync client.
        url: Validated bulk URL or configured Scryfall manifest endpoint.
        limit: Maximum raw transfer bytes.

    Yields:
        Unmodified bytes; HTTP content encoding other than identity is rejected.

    Raises:
        ValueError: For unsupported encoding or oversized content.
        httpx.HTTPError: For network failures, redirects, or unsuccessful responses.
    """
    size = 0
    async with client.stream(
        "GET", url, headers={"Accept-Encoding": "identity"}, follow_redirects=False
    ) as response:
        response.raise_for_status()
        if response.headers.get("Content-Encoding", "identity").strip().lower() != "identity":
            raise ValueError("Unexpected Scryfall HTTP content encoding; retain last-good sources")
        async for chunk in response.aiter_raw():
            size += len(chunk)
            if size > limit:
                raise ValueError(f"Scryfall download exceeds byte limit {limit}; retain sources")
            yield chunk


async def fetch_exports(client: httpx.AsyncClient) -> dict[ExportKind, BulkExport]:
    """Fetch all required receipts from one manifest; never silently omit a source.

    Args:
        client: Existing Scryfall sync HTTP client.

    Returns:
        Validated receipts for cards, printing history, and Oracle tags.

    Raises:
        ValueError: For incomplete, duplicated, or invalid metadata.
        httpx.HTTPError: If the source request fails.
    """
    chunks = [
        chunk
        async for chunk in stream_export(
            client, settings.scryfall_bulk_data_url, _MAX_MANIFEST_BYTES
        )
    ]
    data = json.loads(b"".join(chunks))
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Invalid Scryfall bulk manifest; retain last-good sources")
    exports: dict[ExportKind, BulkExport] = {}
    for row in data["data"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid Scryfall bulk manifest entry; retain last-good sources")
        if row.get("type") not in EXPORT_KINDS:
            continue
        export = BulkExport.model_validate(row)
        if export.type in exports:
            raise ValueError(f"Duplicate Scryfall {export.type} export receipt")
        exports[export.type] = export
    missing = set(EXPORT_KINDS) - exports.keys()
    if missing:
        raise ValueError(f"Missing Scryfall bulk exports: {', '.join(sorted(missing))}")
    return exports


async def download_export(client: httpx.AsyncClient, export: BulkExport, limit: int) -> bytes:
    """Collect a bounded compressed file without allowing implicit HTTP decompression.

    Args:
        client: Existing sync client.
        export: Validated upstream export receipt.
        limit: Maximum compressed file bytes.

    Returns:
        The unmodified gzip file bytes.

    Raises:
        ValueError: For unsupported HTTP encoding or oversized content.
        httpx.HTTPError: If the request fails or redirects.
    """
    chunks = [chunk async for chunk in stream_export(client, export.jsonl_download_uri, limit)]
    return b"".join(chunks)

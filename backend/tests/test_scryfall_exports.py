"""Bulk receipts and download security/size boundaries use only an in-memory HTTP source."""

import gzip
import json
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from mtg_helper.services.scryfall_exports import (
    EXPORT_KINDS,
    BulkExport,
    download_export,
    fetch_exports,
    stream_export,
)

pytestmark = pytest.mark.no_db


def json_response(body: object) -> httpx.Response:
    return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))


def receipt(kind: str) -> dict:
    return {
        "id": str(UUID(int=100)),
        "object": "bulk_data",
        "type": kind,
        "updated_at": "2026-10-12T00:00:00Z",
        "jsonl_download_uri": f"https://data.scryfall.io/{kind}.jsonl.gz",
        "extra_source_metadata": "preserved",
    }


async def test_one_manifest_retains_all_required_receipts() -> None:
    requests = []

    def response(request: httpx.Request) -> httpx.Response:
        requests.append(request.url)
        return json_response({"data": [receipt(kind) for kind in EXPORT_KINDS]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        exports = await fetch_exports(client)
    assert len(requests) == 1
    assert set(exports) == set(EXPORT_KINDS)
    assert exports["oracle_tags"].model_dump()["extra_source_metadata"] == "preserved"


@pytest.mark.parametrize("kind", EXPORT_KINDS)
async def test_missing_source_cannot_be_silently_skipped(kind: str) -> None:
    rows = [receipt(item) for item in EXPORT_KINDS if item != kind]
    transport = httpx.MockTransport(lambda _: json_response({"data": rows}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="Missing Scryfall bulk exports"):
            await fetch_exports(client)


@pytest.mark.parametrize("body", [[], {}, {"data": None}, {"data": [None]}])
async def test_malformed_manifest_is_rejected(body: object) -> None:
    transport = httpx.MockTransport(lambda _: json_response(body))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="Invalid Scryfall bulk manifest"):
            await fetch_exports(client)


async def test_duplicate_export_receipt_is_rejected() -> None:
    rows = [receipt(kind) for kind in EXPORT_KINDS] + [receipt("oracle_tags")]
    transport = httpx.MockTransport(lambda _: json_response({"data": rows}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="Duplicate Scryfall oracle_tags"):
            await fetch_exports(client)


@pytest.mark.parametrize(
    "url",
    [
        "http://data.scryfall.io/export.gz",
        "https://scryfall.io.evil.example/export.gz",
        "https://fake-scryfall.io/export.gz",
        "https://localhost/export.gz",
        "https://user:password@data.scryfall.io/export.gz",
        "https://data.scryfall.io:1234/export.gz",
        "https://data.scryfall.io/export.gz#fragment",
    ],
)
def test_download_receipt_rejects_untrusted_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="untrusted bulk download URL"):
        BulkExport.model_validate({**receipt("oracle_tags"), "jsonl_download_uri": url})


@pytest.mark.parametrize("field", ["id", "updated_at", "jsonl_download_uri"])
def test_required_receipt_fields_cannot_be_missing(field: str) -> None:
    row = receipt("oracle_tags")
    del row[field]
    with pytest.raises(ValidationError):
        BulkExport.model_validate(row)


async def test_http_compression_is_rejected_before_the_body_is_read() -> None:
    read = []

    class EncodedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            read.append(True)
            yield gzip.compress(b"a" * 8_388_608)

    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=EncodedBody())
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="HTTP content encoding"):
            await download_export(client, BulkExport.model_validate(receipt("oracle_tags")), 1024)
    assert read == []


async def test_download_returns_source_bytes_at_exact_limit() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, stream=httpx.ByteStream(b"12345"))
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert (
            await download_export(client, BulkExport.model_validate(receipt("oracle_tags")), 5)
            == b"12345"
        )


async def test_oversize_download_is_rejected() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, stream=httpx.ByteStream(b"123456"))
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="download exceeds byte limit"):
            await download_export(client, BulkExport.model_validate(receipt("oracle_tags")), 5)


async def test_manifest_transfer_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from mtg_helper.services import scryfall_exports

    monkeypatch.setattr(scryfall_exports, "_MAX_MANIFEST_BYTES", 5)
    transport = httpx.MockTransport(lambda _: json_response({"data": []}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="download exceeds byte limit"):
            await fetch_exports(client)


async def test_http_identity_preserves_raw_gzip_file_bytes() -> None:
    content = gzip.compress(b"source bytes")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"Content-Encoding": "identity"}, stream=httpx.ByteStream(content)
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        assert (
            await download_export(
                client, BulkExport.model_validate(receipt("oracle_tags")), len(content)
            )
            == content
        )


async def test_streaming_limit_stops_without_reading_later_chunks() -> None:
    read = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b"123", b"456", b"789"]:
                read.append(chunk)
                yield chunk

    def response(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, stream=Chunks())

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(ValueError, match="download exceeds byte limit"):
            _ = [chunk async for chunk in stream_export(client, "https://data.scryfall.io/file", 5)]
    assert read == [b"123", b"456"]


async def test_redirect_is_not_followed_even_when_client_follows_redirects() -> None:
    requests = []

    def response(request: httpx.Request) -> httpx.Response:
        requests.append(request.url)
        return httpx.Response(302, headers={"Location": "https://localhost/secret"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(response), follow_redirects=True
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await download_export(client, BulkExport.model_validate(receipt("oracle_tags")), 100)
    assert len(requests) == 1


async def test_network_error_is_not_swallowed() -> None:
    def response(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(httpx.ConnectError, match="offline"):
            await fetch_exports(client)

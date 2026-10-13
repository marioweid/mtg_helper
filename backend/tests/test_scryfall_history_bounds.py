"""Printing history has independent transfer, decompression, line, and record guards."""

import gzip
import io
import json

import httpx
import pytest

from mtg_helper.services.new_cards import catalog

pytestmark = pytest.mark.no_db


def test_history_line_bomb_is_rejected_before_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    content = gzip.compress(json.dumps({"object": "card", "name": "x" * 4_194_304}).encode())
    parsed = []

    def unexpected_parse(value: bytes):
        parsed.append(value)
        raise AssertionError("Oversized history line reached the JSON parser")

    monkeypatch.setattr(catalog.json, "loads", unexpected_parse)
    with pytest.raises(ValueError, match="history exceeds decompression limits"):
        list(catalog._records(io.BytesIO(content)))
    assert parsed == []


def test_history_total_decompression_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    line = b'{"object":"card"}\n'
    monkeypatch.setattr(catalog, "_MAX_HISTORY_BYTES", len(line) * 2)
    with pytest.raises(ValueError, match="history exceeds decompression limits"):
        list(catalog._records(io.BytesIO(gzip.compress(line * 3))))


def test_history_record_count_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "_MAX_HISTORY_RECORDS", 2)
    line = b'{"object":"card"}\n'
    with pytest.raises(ValueError, match="history exceeds record limit"):
        list(catalog._records(io.BytesIO(gzip.compress(line * 3))))


@pytest.mark.parametrize("content", [b"bad gzip", gzip.compress(b"not json")])
def test_bad_history_archive_is_reported(content: bytes) -> None:
    with pytest.raises(ValueError, match="printing-history gzip JSONL"):
        list(catalog._records(io.BytesIO(content)))


@pytest.mark.parametrize("row", [[], {"object": "tag"}])
def test_noncard_history_record_is_rejected(row: object) -> None:
    with pytest.raises(ValueError, match="Invalid Scryfall card record"):
        list(catalog._records(io.BytesIO(gzip.compress(json.dumps(row).encode()))))


async def test_http_encoding_is_rejected_before_history_download() -> None:
    read = []

    class EncodedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            read.append(True)
            yield gzip.compress(b"x" * 8_388_608)

    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=EncodedBody())
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="HTTP content encoding"):
            await catalog.download_history(client, "https://data.scryfall.io/history.gz")
    assert read == []


async def test_history_raw_transfer_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "_MAX_BYTES", 5)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, stream=httpx.ByteStream(b"123456"))
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="download exceeds byte limit"):
            await catalog.download_history(client, "https://data.scryfall.io/history.gz")


async def test_too_small_history_cannot_be_published() -> None:
    content = gzip.compress(b'{"object":"card"}\n')
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=httpx.ByteStream(content)))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="history is empty or unexpectedly small"):
            await catalog.download_history(client, "https://data.scryfall.io/history.gz")


@pytest.mark.parametrize(
    "url", ["https://user:password@data.scryfall.io/file.gz", "https://localhost/history.gz"]
)
async def test_bad_history_url_is_rejected_without_a_request(url: str) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Untrusted history URL reached HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        with pytest.raises(ValueError, match="untrusted bulk download URL"):
            await catalog.download_history(client, url)

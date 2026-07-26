"""Import a collection from a Moxfield binder URL.

Pipeline: parse the URL into a binder public id → fetch the binder's card
pages from the Moxfield API → translate entries into ``ParsedCollectionRow``
rows that the shared :func:`mtg_helper.services.collection_service.import_rows`
backend persists.

Moxfield's trade-binder API is undocumented and occasionally shifts shape;
the fetch/translate layer is intentionally defensive — missing fields are
ignored, not asserted.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import asyncpg
import httpx
from curl_cffi.requests.errors import RequestsError

from mtg_helper.config import settings
from mtg_helper.models.collections import CollectionImportResponse, CollectionResponse
from mtg_helper.services import collection_service
from mtg_helper.services.collection_service import ParsedCollectionRow
from mtg_helper.services.deck_url_import_service import (
    _close_client,
    _looks_like_cloudflare,
    _make_client,
)

_log = logging.getLogger(__name__)

_PAGE_SIZE = 100
_MAX_BINDER_PAGES = 200

# URL → binder public id. Allow trailing path segments (slug, subroute).
_MOXFIELD_BINDER_URL = re.compile(
    r"^https?://(?:www\.)?moxfield\.com/binders/(?P<id>[A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)


class UnsupportedBinderUrlError(ValueError):
    """Raised when the URL is not a Moxfield binder URL."""


class BinderFetchError(RuntimeError):
    """Raised when the Moxfield binder fetch fails or returns unparseable data."""


@dataclass
class FetchedBinder:
    """Source representation of a fetched Moxfield binder."""

    binder_id: str
    name: str | None = None
    rows: list[ParsedCollectionRow] = field(default_factory=list)


def parse_binder_url(url: str) -> str:
    """Extract the binder public id from a Moxfield binder URL.

    Args:
        url: A full ``https://`` URL pointing at a public Moxfield binder.

    Returns:
        The binder's public id (the slug after ``/binders/``).

    Raises:
        UnsupportedBinderUrlError: When the URL is not a Moxfield binder URL.
    """
    m = _MOXFIELD_BINDER_URL.match(url.strip())
    if m:
        return m.group("id")
    raise UnsupportedBinderUrlError(
        "Only Moxfield binder URLs are supported. Expected something like "
        "'https://www.moxfield.com/binders/<id>'."
    )


# ── Entry translation ────────────────────────────────────────────────────────


_FOIL_FINISHES = frozenset({"foil", "etched"})


def _condition_title(raw: Any) -> str | None:
    """Convert a Moxfield camelCase condition ('nearMint') to 'Near Mint'."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw.strip())
    return spaced.title()


def _entry_foil(entry: dict[str, Any]) -> bool:
    """A binder entry counts as foil when flagged or has a foil/etched finish."""
    if entry.get("isFoil") is True:
        return True
    finish = entry.get("finish")
    return isinstance(finish, str) and finish.strip().lower() in _FOIL_FINISHES


def _entry_price(raw: Any) -> Decimal | None:
    """Purchase price as Decimal; Moxfield stores unset prices as 0 → None."""
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def _entry_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _entry_language(entry: dict[str, Any]) -> str | None:
    lang = entry.get("language")
    if not isinstance(lang, dict):
        return None
    name = lang.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _entry_quantity(raw: Any) -> int:
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _str_field(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _entry_scryfall_id(card: dict[str, Any]) -> UUID | None:
    raw = card.get("scryfall_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return UUID(raw.strip())
    except ValueError:
        return None


def _binder_entry_row(entry: dict[str, Any]) -> ParsedCollectionRow | None:
    """Translate one Moxfield binder entry into a ParsedCollectionRow.

    Returns None when the entry carries no usable card name.
    """
    card = entry.get("card")
    if not isinstance(card, dict):
        return None
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return ParsedCollectionRow(
        name=name.strip(),
        quantity=_entry_quantity(entry.get("quantity")),
        set_code=_str_field(card, "set"),
        collector_number=_str_field(card, "cn"),
        foil=_entry_foil(entry),
        condition=_condition_title(entry.get("condition")),
        language=_entry_language(entry),
        tags=[],
        purchase_price=_entry_price(entry.get("purchasePrice")),
        last_modified=_entry_datetime(entry.get("lastUpdatedAtUtc")),
        scryfall_id=_entry_scryfall_id(card),
    )


# ── Fetch ────────────────────────────────────────────────────────────────────


async def _fetch_binder_page(binder_id: str, page: int, *, client: Any) -> dict[str, Any]:
    """Fetch one binder page, translating upstream failures into BinderFetchError."""
    url = (
        f"{settings.moxfield_base_url}/v1/trade-binders/{binder_id}"
        f"?pageNumber={page}&pageSize={_PAGE_SIZE}"
    )
    try:
        response = await client.get(url)
    except (httpx.HTTPError, RequestsError) as exc:
        raise BinderFetchError(f"Could not reach Moxfield: {exc}") from exc
    if response.status_code in (401, 403, 503) and _looks_like_cloudflare(response):
        raise BinderFetchError(
            "Moxfield is currently blocking automated imports (Cloudflare "
            "challenge). Export the binder as a CSV on moxfield.com and use "
            "the CSV import instead."
        )
    if response.status_code in (401, 403):
        raise BinderFetchError(
            "Moxfield blocked the request — the binder may be private or rate "
            "limits are in effect. Try again in a minute."
        )
    if response.status_code == 404:
        raise BinderFetchError(f"Moxfield binder '{binder_id}' was not found.")
    if response.status_code >= 400:
        raise BinderFetchError(
            f"Moxfield returned status {response.status_code} for binder '{binder_id}'."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise BinderFetchError("Moxfield response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise BinderFetchError("Moxfield response had an unexpected shape.")
    return payload


def _binder_name(payload: dict[str, Any]) -> str | None:
    meta = payload.get("tradeBinder")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("name")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _total_pages(payload: dict[str, Any]) -> int:
    raw = payload.get("totalPages")
    return raw if isinstance(raw, int) and raw >= 1 else 1


def _page_rows(payload: dict[str, Any]) -> list[ParsedCollectionRow]:
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise BinderFetchError("Moxfield response had an unexpected shape.")
    rows: list[ParsedCollectionRow] = []
    for entry in entries:
        if isinstance(entry, dict):
            row = _binder_entry_row(entry)
            if row is not None:
                rows.append(row)
    return rows


async def fetch_moxfield_binder(binder_id: str, *, client: Any) -> FetchedBinder:
    """Fetch and translate a full Moxfield binder (all pages).

    Calls ``GET {moxfield_base_url}/v1/trade-binders/{binder_id}`` once per
    page until every row is collected, with a short politeness delay
    (``moxfield_binder_page_delay_seconds``) between page requests.

    Args:
        binder_id: Moxfield binder public id (the slug from the URL).
        client: Injected HTTP client. Production uses curl_cffi's
            ``AsyncSession`` impersonating Chrome (Moxfield is behind
            Cloudflare); tests inject ``httpx.AsyncClient`` with a mock
            transport.

    Returns:
        FetchedBinder with the binder name and all rows translated to
        ParsedCollectionRow entries.

    Raises:
        BinderFetchError: On upstream errors, invalid payloads, or when the
            page cap is exceeded.
    """
    rows: list[ParsedCollectionRow] = []
    name: str | None = None
    page = 1
    total_pages = 1
    while page <= total_pages:
        if page > _MAX_BINDER_PAGES:
            raise BinderFetchError(
                f"Binder '{binder_id}' exceeds the {_MAX_BINDER_PAGES}-page import cap."
            )
        payload = await _fetch_binder_page(binder_id, page, client=client)
        name = name or _binder_name(payload)
        rows.extend(_page_rows(payload))
        total_pages = _total_pages(payload)
        page += 1
        if page <= total_pages:
            await asyncio.sleep(settings.moxfield_binder_page_delay_seconds)
    return FetchedBinder(binder_id=binder_id, name=name, rows=rows)


# ── Orchestration ────────────────────────────────────────────────────────────


async def _fetch_with_client(url: str, client: Any) -> FetchedBinder:
    """Parse the URL and fetch the binder, closing owned clients afterwards."""
    binder_id = parse_binder_url(url)
    owned_client = client is None
    http_client = client or _make_client()
    try:
        return await fetch_moxfield_binder(binder_id, client=http_client)
    finally:
        if owned_client:
            await _close_client(http_client)


async def import_from_url(
    pool: asyncpg.Pool,
    collection_id: UUID,
    url: str,
    mode: str,
    *,
    client: Any = None,
) -> CollectionImportResponse:
    """Fetch a Moxfield binder URL and import its rows into an existing collection.

    Args:
        pool: asyncpg connection pool.
        collection_id: Target collection UUID.
        url: Binder URL pasted by the user.
        mode: 'merge' or 'replace' (same semantics as the CSV import).
        client: Optional injected HTTP client (tests).

    Returns:
        CollectionImportResponse with per-operation counts and unresolved names.

    Raises:
        UnsupportedBinderUrlError: If the URL is not a Moxfield binder URL.
        BinderFetchError: If the upstream fetch fails.
        CollectionNotFoundError: If the collection does not exist.
    """
    fetched = await _fetch_with_client(url, client)
    _log.info(
        "Importing Moxfield binder %s ('%s') into collection %s: %d rows, mode=%s",
        fetched.binder_id,
        fetched.name,
        collection_id,
        len(fetched.rows),
        mode,
    )
    return await collection_service.import_rows(
        pool, collection_id, fetched.rows, mode, source="moxfield-url"
    )


async def import_new_from_url(
    pool: asyncpg.Pool,
    url: str,
    account_id: UUID,
    *,
    name: str | None = None,
    client: Any = None,
) -> tuple[CollectionResponse, CollectionImportResponse]:
    """Create a collection from a Moxfield binder URL and import its rows.

    The collection is named after ``name`` when given, then the binder's
    Moxfield name, falling back to 'Moxfield binder'.

    Args:
        pool: asyncpg connection pool.
        url: Binder URL pasted by the user.
        account_id: Owner account UUID for the new collection.
        name: Optional collection name override.
        client: Optional injected HTTP client (tests).

    Returns:
        Tuple of (created collection, re-fetched after the import so its
        card_count reflects the imported rows, import response).

    Raises:
        UnsupportedBinderUrlError: If the URL is not a Moxfield binder URL.
        BinderFetchError: If the upstream fetch fails.
        DuplicateCollectionNameError: If the account already owns the name.
    """
    fetched = await _fetch_with_client(url, client)
    collection_name = name or fetched.name or "Moxfield binder"
    collection = await collection_service.create_collection(pool, account_id, collection_name)
    result = await collection_service.import_rows(
        pool, collection.id, fetched.rows, "replace", source="moxfield-url"
    )
    return await collection_service.get_collection(pool, collection.id), result

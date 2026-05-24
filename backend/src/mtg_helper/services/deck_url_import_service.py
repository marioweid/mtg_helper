"""Import a deck from a Moxfield or Archidekt deck URL.

Pipeline: parse the URL into ``(source, deck_id)`` → fetch the source's deck
JSON via httpx → translate the response into ``ParsedCard`` entries that the
existing :func:`mtg_helper.services.import_service.import_parsed_entries`
backend can persist.

The two source-specific fetchers are intentionally defensive — Moxfield and
Archidekt both serve undocumented public JSON that occasionally shifts shape.
Missing fields are ignored, not asserted.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests.errors import RequestsError

from mtg_helper.config import settings
from mtg_helper.models.decks import DeckImportResponse
from mtg_helper.services import import_service
from mtg_helper.services.import_service import _SECTION_TO_CATEGORY, ParsedCard

_log = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30.0

# Moxfield's API sits behind Cloudflare's bot challenge — plain httpx hits a
# 403 + JS challenge HTML page. ``curl_cffi`` impersonates Chrome's TLS/JA3
# fingerprint at the libcurl layer, which is what the challenge actually
# checks. ``httpx`` is still used for non-Cloudflare sources (Archidekt).
_IMPERSONATE_TARGET = "chrome"

# URL → (source, deck_id). Allow trailing path segments (slug, subroute).
_MOXFIELD_URL = re.compile(
    r"^https?://(?:www\.)?moxfield\.com/decks/(?P<id>[A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)
_ARCHIDEKT_URL = re.compile(
    r"^https?://(?:www\.)?archidekt\.com/decks/(?P<id>\d+)(?:[/#?].*)?$",
    re.IGNORECASE,
)


class UnsupportedDeckUrlError(ValueError):
    """Raised when the URL doesn't match any supported source."""


class DeckFetchError(RuntimeError):
    """Raised when the upstream source returns an error or unparseable body."""


@dataclass
class FetchedDeck:
    """Source-agnostic representation of a fetched deck."""

    source: str
    source_deck_id: str
    name: str | None = None
    description: str | None = None
    commanders: list[str] = field(default_factory=list)
    entries: list[ParsedCard] = field(default_factory=list)


def parse_deck_url(url: str) -> tuple[str, str]:
    """Identify the source and deck id of a deck URL.

    Args:
        url: A full ``https://`` URL pointing at a deck on a supported site.

    Returns:
        Tuple of ``(source, deck_id)`` where ``source`` is ``"moxfield"`` or
        ``"archidekt"``.

    Raises:
        UnsupportedDeckUrlError: When the URL does not match any supported
            source's deck route.
    """
    cleaned = url.strip()
    m = _MOXFIELD_URL.match(cleaned)
    if m:
        return "moxfield", m.group("id")
    m = _ARCHIDEKT_URL.match(cleaned)
    if m:
        return "archidekt", m.group("id")
    raise UnsupportedDeckUrlError(
        "Only Moxfield and Archidekt deck URLs are supported. Expected something "
        "like 'https://www.moxfield.com/decks/<id>' or "
        "'https://archidekt.com/decks/<id>'."
    )


_CLOUDFLARE_HTML_MARKERS = (
    "Attention Required! | Cloudflare",
    "challenge-platform",
    "cf-error-details",
)


def _looks_like_cloudflare(response: Any) -> bool:
    """Detect a Cloudflare bot-challenge HTML body.

    The challenge page is served with 403 (sometimes 503) and an HTML body
    with characteristic markers. Distinguishing it from a private-deck 403
    lets us surface a different, paste-text-friendly error.
    """
    body = getattr(response, "text", "") or ""
    if not body or len(body) < 50:
        return False
    snippet = body[:2000]
    return any(marker in snippet for marker in _CLOUDFLARE_HTML_MARKERS)


# ── Moxfield ─────────────────────────────────────────────────────────────────


# Moxfield labels each entry with a top-level card.type ("Creature", "Land", …).
# Map those onto the section categories the import pipeline already knows.
_MOXFIELD_TYPE_TO_CATEGORY: dict[str, str] = {
    "creature": "theme",
    "artifact": "theme",
    "enchantment": "theme",
    "planeswalker": "theme",
    "battle": "theme",
    "instant": "interaction",
    "sorcery": "interaction",
    "land": "lands",
}


def _moxfield_category(card_type: str | None) -> str | None:
    """Map a Moxfield ``card.type`` field onto an internal section category."""
    if not card_type:
        return None
    first = card_type.strip().split()[0].lower() if card_type.strip() else ""
    return _MOXFIELD_TYPE_TO_CATEGORY.get(first)


def _moxfield_card_name(entry: dict[str, Any]) -> str | None:
    """Extract the card name from a Moxfield board entry."""
    card = entry.get("card") or {}
    name = card.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


async def fetch_moxfield_deck(deck_id: str, *, client: Any) -> FetchedDeck:
    """Fetch and translate a Moxfield deck.

    Calls ``GET {moxfield_base_url}/v3/decks/all/{deck_id}`` and walks
    ``boards.commanders`` and ``boards.mainboard``. Sideboard, maybeboard,
    tokens, considering, and similar zones are ignored — only mainboard and
    commander entries become :class:`ParsedCard` rows.

    Args:
        deck_id: Moxfield public deck id (the slug from the URL).
        client: Injected HTTP client. Production uses curl_cffi's
            ``AsyncSession`` impersonating Chrome (Moxfield is behind
            Cloudflare); tests inject ``httpx.AsyncClient`` with a mock
            transport. Both expose ``.get()`` returning a response with
            ``.status_code``, ``.text``, and ``.json()``.

    Returns:
        FetchedDeck with ``source='moxfield'``.

    Raises:
        DeckFetchError: On any non-success status, transient network error, or
            non-JSON body.
    """
    url = f"{settings.moxfield_base_url}/v3/decks/all/{deck_id}"
    try:
        response = await client.get(url)
    except (httpx.HTTPError, RequestsError) as exc:
        raise DeckFetchError(f"Could not reach Moxfield: {exc}") from exc
    if response.status_code in (401, 403, 503) and _looks_like_cloudflare(response):
        raise DeckFetchError(
            "Moxfield is currently blocking automated imports (Cloudflare "
            "challenge). Open the deck on moxfield.com, copy the deck list, "
            "and use 'Paste deck text' instead."
        )
    if response.status_code in (401, 403):
        raise DeckFetchError(
            "Moxfield blocked the request — the deck may be private or rate "
            "limits are in effect. Try again in a minute."
        )
    if response.status_code == 404:
        raise DeckFetchError(f"Moxfield deck '{deck_id}' was not found.")
    if response.status_code >= 400:
        raise DeckFetchError(
            f"Moxfield returned status {response.status_code} for deck '{deck_id}'."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise DeckFetchError("Moxfield response was not valid JSON") from exc

    boards = payload.get("boards") or {}
    commanders = _moxfield_extract_commanders(boards)
    entries = _moxfield_extract_mainboard(boards)
    return FetchedDeck(
        source="moxfield",
        source_deck_id=deck_id,
        name=payload.get("name"),
        description=payload.get("description"),
        commanders=commanders,
        entries=entries,
    )


def _moxfield_extract_commanders(boards: dict[str, Any]) -> list[str]:
    """Pull commander names from the ``commanders`` board (plus companion fallback)."""
    names: list[str] = []
    cmd_board = (boards.get("commanders") or {}).get("cards") or {}
    for entry in cmd_board.values():
        name = _moxfield_card_name(entry)
        if name:
            names.append(name)
    return names


def _moxfield_extract_mainboard(boards: dict[str, Any]) -> list[ParsedCard]:
    """Pull mainboard entries with quantities + category hints."""
    main = (boards.get("mainboard") or {}).get("cards") or {}
    entries: list[ParsedCard] = []
    for entry in main.values():
        name = _moxfield_card_name(entry)
        if not name:
            continue
        qty_raw = entry.get("quantity") or 1
        try:
            qty = max(1, int(qty_raw))
        except (TypeError, ValueError):
            qty = 1
        card_type = (entry.get("card") or {}).get("type")
        entries.append(
            ParsedCard(
                name=name,
                quantity=qty,
                is_commander=False,
                category=_moxfield_category(card_type),
            )
        )
    return entries


# ── Archidekt ────────────────────────────────────────────────────────────────


_ARCHIDEKT_SKIP_CATEGORIES = frozenset({"sideboard", "maybeboard", "tokens", "considering"})


def _archidekt_category(categories: list[str]) -> str | None:
    """Map Archidekt's per-card category list onto an internal section category.

    Archidekt cards carry a free-form ``categories`` array (e.g. ``["Ramp"]``).
    Pick the first non-Commander entry that maps to a known section.
    """
    for raw in categories:
        if not isinstance(raw, str):
            continue
        lowered = raw.strip().lower()
        if lowered == "commander":
            continue
        mapped = _SECTION_TO_CATEGORY.get(lowered)
        if mapped is not None:
            return mapped
    return None


def _archidekt_should_skip(categories: list[str]) -> bool:
    """Skip cards whose category set indicates they aren't mainboard."""
    for raw in categories:
        if isinstance(raw, str) and raw.strip().lower() in _ARCHIDEKT_SKIP_CATEGORIES:
            return True
    return False


async def fetch_archidekt_deck(deck_id: str, *, client: Any) -> FetchedDeck:
    """Fetch and translate an Archidekt deck.

    Calls ``GET {archidekt_base_url}/decks/{deck_id}/`` and iterates the
    ``cards`` array. Cards in Sideboard / Maybeboard / Tokens / Considering
    categories are skipped. Cards with a ``Commander`` category become commanders.

    Args:
        deck_id: Archidekt numeric deck id from the URL.
        client: Injected HTTP client (curl_cffi or httpx, both compatible).

    Returns:
        FetchedDeck with ``source='archidekt'``.

    Raises:
        DeckFetchError: On any non-success status, transient network error, or
            non-JSON body.
    """
    url = f"{settings.archidekt_base_url}/decks/{deck_id}/"
    try:
        response = await client.get(url)
    except (httpx.HTTPError, RequestsError) as exc:
        raise DeckFetchError(f"Could not reach Archidekt: {exc}") from exc
    if response.status_code == 404:
        raise DeckFetchError(f"Archidekt deck '{deck_id}' was not found.")
    if response.status_code in (401, 403):
        raise DeckFetchError("Archidekt blocked the request — the deck may be private.")
    if response.status_code >= 400:
        raise DeckFetchError(
            f"Archidekt returned status {response.status_code} for deck '{deck_id}'."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise DeckFetchError("Archidekt response was not valid JSON") from exc

    cards = payload.get("cards") or []
    commanders, entries = _archidekt_split_cards(cards)
    return FetchedDeck(
        source="archidekt",
        source_deck_id=deck_id,
        name=payload.get("name"),
        description=payload.get("description"),
        commanders=commanders,
        entries=entries,
    )


def _archidekt_split_cards(
    cards: list[dict[str, Any]],
) -> tuple[list[str], list[ParsedCard]]:
    """Split an Archidekt ``cards`` payload into commanders and mainboard entries."""
    commanders: list[str] = []
    entries: list[ParsedCard] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        oracle = card.get("card") or {}
        oracle_card = oracle.get("oracleCard") or {}
        name = oracle_card.get("name") or oracle.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        categories = card.get("categories") or []
        if not isinstance(categories, list):
            categories = []
        if _archidekt_should_skip(categories):
            continue
        is_commander = any(
            isinstance(c, str) and c.strip().lower() == "commander" for c in categories
        )
        qty_raw = card.get("quantity") or 1
        try:
            qty = max(1, int(qty_raw))
        except (TypeError, ValueError):
            qty = 1
        if is_commander:
            commanders.append(name.strip())
            continue
        entries.append(
            ParsedCard(
                name=name.strip(),
                quantity=qty,
                is_commander=False,
                category=_archidekt_category(categories),
            )
        )
    return commanders, entries


# ── Orchestration ────────────────────────────────────────────────────────────


def _make_client() -> Any:
    """Create the production HTTP client (Chrome-impersonating curl_cffi).

    Tests inject ``httpx.AsyncClient`` directly; this factory only fires in
    production. Both clients expose the subset of the API we use.
    """
    return CurlAsyncSession(impersonate=_IMPERSONATE_TARGET, timeout=_REQUEST_TIMEOUT)


async def _close_client(client: Any) -> None:
    """Close an owned client regardless of whether it's httpx or curl_cffi."""
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close = getattr(client, "close", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            await result


async def import_from_url(
    pool: asyncpg.Pool,
    url: str,
    email: str,
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    bracket: int = 3,
    client: Any = None,
) -> DeckImportResponse:
    """Fetch a deck from a Moxfield/Archidekt URL and persist it locally.

    Args:
        pool: asyncpg connection pool.
        url: Deck URL pasted by the user.
        email: Authenticated account email — owner of the new deck.
        name_override: Optional deck name; falls back to the source's name,
            then to a generic placeholder.
        description_override: Optional description; falls back to source's.
        bracket: Deck bracket (1–5); defaults to 3.
        client: Optional httpx client (injected by tests).

    Returns:
        DeckImportResponse with the created deck and per-card results.

    Raises:
        UnsupportedDeckUrlError: If the URL is not from a supported source.
        DeckFetchError: If the upstream fetch fails.
        CardNotFoundError: If the commander cannot be resolved locally.
    """
    source, deck_id = parse_deck_url(url)
    owned_client = client is None
    http_client = client or _make_client()
    try:
        if source == "moxfield":
            fetched = await fetch_moxfield_deck(deck_id, client=http_client)
        else:
            fetched = await fetch_archidekt_deck(deck_id, client=http_client)
    finally:
        if owned_client:
            await _close_client(http_client)

    if not fetched.commanders:
        raise DeckFetchError(
            f"No commander was found in the {source} deck. The deck may be "
            "missing a commander designation."
        )

    commander_entries = [ParsedCard(name=name, is_commander=True) for name in fetched.commanders]
    name = name_override or fetched.name or f"Imported {source} deck"
    description = description_override or fetched.description

    _log.info(
        "Importing %s deck %s as '%s' (%d entries, %d commanders)",
        source,
        deck_id,
        name,
        len(fetched.entries),
        len(fetched.commanders),
    )
    return await import_service.import_parsed_entries(
        pool,
        commanders=commander_entries,
        non_commanders=fetched.entries,
        name=name,
        description=description,
        bracket=bracket,
        email=email,
    )

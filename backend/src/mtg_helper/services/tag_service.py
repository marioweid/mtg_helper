"""Rule-based card tag classification pipeline."""

import asyncio
import logging
import re
import time
from typing import Any

import asyncpg
from qdrant_client import AsyncQdrantClient

_log = logging.getLogger(__name__)

_BATCH_SIZE = 500
_QDRANT_CONCURRENCY = 50

# Fast-mana cards: low-CMC mana producers that give more mana than they cost.
_FAST_MANA_NAMES = frozenset(
    {
        "Sol Ring",
        "Mana Crypt",
        "Mana Vault",
        "Grim Monolith",
        "Chrome Mox",
        "Mox Diamond",
        "Mox Opal",
        "Mox Amber",
        "Jeweled Lotus",
        "Lotus Petal",
        "Black Lotus",
        "Ancient Tomb",
        "City of Traitors",
        "Elvish Spirit Guide",
        "Simian Spirit Guide",
        "Lion's Eye Diamond",
        "Mishra's Workshop",
        "Tolarian Academy",
    }
)


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_PAT_RAMP_ADD = _re(r"\{T\}[^.]*add \{|add \{[WUBRGCX]")
_PAT_RAMP_LAND = _re(r"search your library for (?:a |an )?(?:basic |snow |[\w]+ )?land")
_PAT_DRAW = _re(r"draw (?:a card|(?:two|three|four|X|\d+) cards)|each player draws")
_PAT_DESTROY_TARGET = _re(r"destroy target")
_PAT_EXILE_TARGET = _re(r"exile target")
_PAT_DAMAGE_TARGET = _re(
    r"deals? \d+ damage to (?:any target|target creature|target player|target planeswalker)"
)
_PAT_DESTROY_ALL = _re(r"destroy all")
_PAT_EXILE_ALL = _re(r"exile all")
_PAT_MINUS_ALL = _re(r"get -\d+/-\d+ until end of turn")
_PAT_COUNTER = _re(
    r"counter target (?:spell|activated|triggered|noncreature"
    r"|artifact|enchantment|instant|sorcery)"
)
_PAT_TUTOR = _re(r"search your library for (?!(?:a |an )?(?:basic |snow )?land\b)")
_PAT_TOKEN = _re(r"create (?:a |an |\d+ |X )[\w ,/]*token")
_PAT_PLUS_ONE = _re(r"\+1/\+1 counter")
_PAT_LIFEGAIN = _re(r"you gain \d+ life|gain \d+ life|gains? \d+ life")
_PAT_GRAVEYARD = _re(r"from (?:your |a )?graveyard|return [\w ,']+ from (?:your )?graveyard")
_PAT_SACRIFICE = _re(r"sacrifice (?:a |an |another |this |one |two )")
_PAT_DEATH_TRIGGER = _re(r"whenever (?:a |another )?(?:creature |[\w]+ )?dies|when [\w ,']+ dies")
_PAT_BLINK = _re(r"exile [\w ,']+then return [\w ,']+ to the battlefield|flicker")
_PAT_STAX = _re(
    r"(?:opponents?|players?) can't (?:cast|activate|play|attack|block)"
    r"|costs? \{[0-9]+\} more to (?:cast|activate|play)"
)
_PAT_GROUP_HUG = _re(
    r"each player (?:draws|gains|gets|may|puts)|each opponent (?:draws|gains|gets|may)"
)
_PAT_MILL = _re(
    r"\bmill\b|put the top \d+ cards? of (?:your|their|a player's) library"
    r" into (?:your|their|a player's|that player's) graveyard"
)
_PAT_PROTECTION = _re(r"\bhexproof\b|\bshroud\b|\bindestructible\b|protection from")
_PAT_VOLTRON_EQUIP = _re(r"equipped creature gets? \+|equip \{")
_PAT_VOLTRON_AURA = _re(r"enchanted creature gets? \+")
_PAT_EXTRA_TURN = _re(r"take an extra turn|takes? an extra turn")
_PAT_LAND_DESTROY = _re(r"destroy target land|destroy all lands?|destroy each land")
_PAT_TRIBAL = _re(r"\btribal\b")


def _tag_ramp(text: str, tl: str, tags: list[str]) -> None:
    if _PAT_RAMP_ADD.search(text) or _PAT_RAMP_LAND.search(text):
        tags.append("ramp")


def _tag_draw(text: str, tags: list[str]) -> None:
    if _PAT_DRAW.search(text):
        tags.append("draw")


def _tag_removal(text: str, tags: list[str]) -> None:
    if (
        _PAT_DESTROY_TARGET.search(text)
        or _PAT_EXILE_TARGET.search(text)
        or _PAT_DAMAGE_TARGET.search(text)
    ):
        tags.append("removal")


def _tag_board_wipe(text: str, tags: list[str]) -> None:
    if _PAT_DESTROY_ALL.search(text) or _PAT_EXILE_ALL.search(text) or _PAT_MINUS_ALL.search(text):
        tags.append("board_wipe")


def _tag_tutor_token_counter(text: str, tags: list[str]) -> None:
    if _PAT_COUNTER.search(text):
        tags.append("counterspell")
    if _PAT_TUTOR.search(text):
        tags.append("tutor")
    if _PAT_TOKEN.search(text):
        tags.append("token")


def _tag_graveyard_sacrifice(text: str, tags: list[str]) -> None:
    if _PAT_PLUS_ONE.search(text):
        tags.append("plus_one_counters")
    if _PAT_LIFEGAIN.search(text):
        tags.append("lifegain")
    if _PAT_GRAVEYARD.search(text):
        tags.append("graveyard")
    has_sacrifice = bool(_PAT_SACRIFICE.search(text))
    has_death = bool(_PAT_DEATH_TRIGGER.search(text))
    if has_sacrifice:
        tags.append("sacrifice")
    if has_sacrifice and has_death:
        tags.append("aristocrats")


def _tag_equipment_voltron(tl: str, text: str, tags: list[str]) -> None:
    is_equipment = "equipment" in tl.lower()
    is_aura = "aura" in tl.lower() and "enchantment" in tl.lower()
    if is_equipment:
        tags.append("equipment")
    voltron = (is_equipment and bool(_PAT_VOLTRON_EQUIP.search(text))) or (
        is_aura and bool(_PAT_VOLTRON_AURA.search(text))
    )
    if voltron:
        tags.append("voltron")


def _is_fast_mana(name: str, text: str, cmc: float | None, tags: list[str]) -> bool:
    return name in _FAST_MANA_NAMES or (
        "ramp" in tags and cmc is not None and cmc <= 2 and bool(_PAT_RAMP_ADD.search(text))
    )


def _has_protection(text: str, kw_set: set[str]) -> bool:
    return bool(_PAT_PROTECTION.search(text)) or any(
        k in kw_set for k in ("hexproof", "shroud", "indestructible")
    )


def _tag_stax_hug_mana(name: str, text: str, cmc: float | None, tags: list[str]) -> None:
    if _PAT_STAX.search(text):
        tags.append("stax")
    if _PAT_GROUP_HUG.search(text):
        tags.append("group_hug")
    if _is_fast_mana(name, text, cmc, tags):
        tags.append("fast_mana")
    if _PAT_BLINK.search(text):
        tags.append("blink")
    if _PAT_MILL.search(text):
        tags.append("mill")


def _tag_protection_misc(text: str, tl: str, kw_set: set[str], tags: list[str]) -> None:
    if _has_protection(text, kw_set):
        tags.append("protection")
    if _PAT_EXTRA_TURN.search(text):
        tags.append("extra_turn")
    if _PAT_LAND_DESTROY.search(text):
        tags.append("land_destruction")
    if _PAT_TRIBAL.search(tl):
        tags.append("tribal")


def classify_card(
    name: str,
    type_line: str | None,
    oracle_text: str | None,
    keywords: list[str],
    cmc: float | None,
) -> list[str]:
    """Classify a card into one or more tags using rule-based heuristics.

    Args:
        name: Card name.
        type_line: Type line (e.g. "Legendary Creature — Dragon").
        oracle_text: Rules text.
        keywords: MTG keyword abilities list.
        cmc: Converted mana cost.

    Returns:
        List of tag strings (may be empty for vanilla/complex cards).
    """
    text = oracle_text or ""
    tl = type_line or ""
    kw_set = {k.lower() for k in keywords}
    tags: list[str] = []

    _tag_ramp(text, tl, tags)
    _tag_draw(text, tags)
    _tag_removal(text, tags)
    _tag_board_wipe(text, tags)
    _tag_tutor_token_counter(text, tags)
    _tag_graveyard_sacrifice(text, tags)
    _tag_equipment_voltron(tl, text, tags)
    _tag_stax_hug_mana(name, text, cmc, tags)
    _tag_protection_misc(text, tl, kw_set, tags)

    return tags


async def _sync_tags_to_qdrant(pool: asyncpg.Pool, qdrant_client: AsyncQdrantClient) -> None:
    """Push updated tags from Postgres into Qdrant point payloads.

    Uses concurrent set_payload calls in batches to avoid 30k sequential
    round-trips.

    Args:
        pool: asyncpg connection pool.
        qdrant_client: Async Qdrant client.
    """
    from mtg_helper.config import settings

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, tags FROM cards WHERE embedded_at IS NOT NULL")

    _log.info("Syncing %d card tags to Qdrant", len(rows))

    async def _update_one(card_id: Any, tags: list[str]) -> None:
        await qdrant_client.set_payload(
            collection_name=settings.qdrant_collection,
            payload={"tags": tags},
            points=[str(card_id)],
        )

    for i in range(0, len(rows), _QDRANT_CONCURRENCY):
        chunk = rows[i : i + _QDRANT_CONCURRENCY]
        await asyncio.gather(*[_update_one(r["id"], list(r["tags"])) for r in chunk])


async def run_batch_tag(
    pool: asyncpg.Pool,
    qdrant_client: AsyncQdrantClient | None = None,
) -> dict[str, Any]:
    """Classify all cards and persist their tags to the database.

    Re-classifies all cards on every run so tag rule changes are fully applied.
    When qdrant_client is provided, also refreshes the tags payload on each
    Qdrant point after the DB update completes.

    Args:
        pool: asyncpg connection pool.
        qdrant_client: Optional Qdrant client for payload sync.

    Returns:
        Summary dict with cards_tagged and duration_seconds.
    """
    start = time.monotonic()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, type_line, oracle_text, keywords, cmc FROM cards ORDER BY name"
        )

    _log.info("Tagging %d cards", len(rows))
    total = 0

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        updates: list[tuple[list[str], Any]] = [
            (
                classify_card(
                    r["name"],
                    r["type_line"],
                    r["oracle_text"],
                    list(r["keywords"]),
                    float(r["cmc"]) if r["cmc"] is not None else None,
                ),
                r["id"],
            )
            for r in batch
        ]

        async with pool.acquire() as conn:
            await conn.executemany(
                "UPDATE cards SET tags = $1 WHERE id = $2",
                updates,
            )

        total += len(batch)

    if qdrant_client is not None:
        await _sync_tags_to_qdrant(pool, qdrant_client)

    _log.info("Tagged %d cards", total)
    return {
        "cards_tagged": total,
        "duration_seconds": round(time.monotonic() - start, 2),
    }

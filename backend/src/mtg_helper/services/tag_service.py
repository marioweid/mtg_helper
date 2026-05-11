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
_PAT_GRAVEYARD = _re(
    r"return [\w ,']+ from (?:your |a )?graveyard"
    r"|put (?:target )?(?:creature |\w+ )?card from (?:your |a )?graveyard"
    r"|reanimate"
)
_PAT_GRAVEYARD_HATE = _re(
    r"exile (?:target |all |each )?(?:card|creature|player'?s? graveyard)"
    r"[\w ,']*?(?:from (?:a |any |target player'?s? |your |each )?graveyard)?"
    r"|if a card would be put into a graveyard from anywhere, exile it instead"
    r"|each opponent exiles? (?:their|his or her) graveyard"
    r"|shuffle [\w ,']+ graveyard into"
)
_PAT_COST_REDUCTION = _re(
    r"costs? \{[0-9XWUBRGC/]+\} less to cast"
    r"|spells? you cast cost \{[0-9XWUBRGC/]+\} less"
)
_PAT_ANTHEM = _re(
    r"creatures? you control get \+\d+/\+\d+"
    r"|other creatures? you control get \+\d+/\+\d+"
)
_PAT_CARD_SELECTION = _re(
    r"\bscry \d+|\bsurveil \d+|\bexplore\b|\bdiscover \d+|\binvestigate\b"
    r"|look at the top \d+ cards? of your library"
)
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
_PAT_ENERGY = _re(r"\{E\}|energy counter")

# New archetype patterns
_PAT_REANIMATOR = _re(
    r"return [\w ,'~\-]+ from (?:your |a |any )?graveyard to the battlefield"
    r"|put [\w ,'~\-]+ from (?:your |a |any )?graveyard onto the battlefield"
    r"|\breanimate\b"
)
_PAT_CASCADE = _re(r"\bcascade\b")
_PAT_STORM = _re(r"\bstorm\b")
_PAT_LANDFALL = _re(
    r"\blandfall\b"
    r"|whenever a land (?:you control )?enters"
    r"|whenever (?:a|one or more) lands? enters? the battlefield under your control"
)
_PAT_SPELLSLINGER = _re(
    r"whenever you cast (?:an?|your) (?:instant|sorcery|noncreature)"
    r"|whenever you cast a spell\b"
)
_PAT_WHEELS = _re(
    r"each player discards (?:their|his or her) hand"
    r"|each player draws \w+ cards?"
    r"|discard your hand, then draw"
)
# Producer + payoff patterns. Moxfield-style chip search expects a Food deck to
# surface both food-makers (Witch's Oven, Peregrin Took) and food-payoffs
# (Trail of Crumbs, sac-food triggers), so we match both sides intentionally.
# The "sacrifice <qty> foods?" clause accepts any quantifier word (a, an, all,
# two, three, another, that many, X) instead of only "a", which missed cards
# like Peregrin Took ("Sacrifice three Foods").
_PAT_TREASURE_CARES = _re(
    r"\bsacrifice (?:\w+\s+){0,2}treasures?\b"
    r"|\btreasures? you control"
    r"|\bwhenever (?:a|one or more) treasure tokens?"
    r"|\bfor each treasure"
    r"|\bcreate (?:\w+\s+){0,3}treasure tokens?"
    r"|\badditional treasure tokens?"
)
_PAT_FOOD_CARES = _re(
    r"\bsacrifice (?:\w+\s+){0,2}foods?\b"
    r"|\bfoods? you control"
    r"|\bwhenever (?:a|one or more) food tokens?"
    r"|\bfor each food"
    r"|\bcreate (?:\w+\s+){0,3}food tokens?"
    r"|\badditional food tokens?"
    # Bloomburrow keyword that always involves sacrificing a Food.
    r"|\bforage\b"
)
_PAT_CLUE_CARES = _re(
    r"\bsacrifice (?:\w+\s+){0,2}clues?\b"
    r"|\bclues? you control"
    r"|\bwhenever (?:a|one or more) clue tokens?"
    r"|\bfor each clue"
    r"|\bcreate (?:\w+\s+){0,3}clue tokens?"
    r"|\badditional clue tokens?"
    # Investigate is the canonical Clue producer keyword; reminder text isn't
    # printed on every card, so we match the bare verb too.
    r"|\binvestigate\b"
)
_PAT_INFECT_TOXIC = _re(r"\binfect\b|\btoxic \d+|poison counter")

# Tribal subtypes worth surfacing as `<subtype>_tribal` mega-tags. Curated to the
# popular EDH archetypes; cards merely *being* the subtype don't qualify — the
# oracle text must scope an effect to the tribe.
_TRIBAL_SUBTYPES: tuple[str, ...] = (
    "Angel",
    "Beast",
    "Bird",
    "Cat",
    "Cleric",
    "Demon",
    "Dinosaur",
    "Dragon",
    "Druid",
    "Dwarf",
    "Elder",
    "Eldrazi",
    "Elemental",
    "Elf",
    "Faerie",
    "Giant",
    "Goblin",
    "Golem",
    "Horror",
    "Human",
    "Insect",
    "Knight",
    "Merfolk",
    "Minotaur",
    "Ninja",
    "Orc",
    "Phoenix",
    "Pirate",
    "Rat",
    "Rogue",
    "Samurai",
    "Shaman",
    "Slime",
    "Sliver",
    "Snake",
    "Soldier",
    "Spider",
    "Spirit",
    "Squirrel",
    "Treefolk",
    "Vampire",
    "Warrior",
    "Werewolf",
    "Wizard",
    "Wolf",
    "Wraith",
    "Wurm",
    "Zombie",
)

# Bumped whenever the tag vocabulary changes — used as a manual signal to
# re-run `/admin/tag-cards` against the corpus. Not auto-enforced.
TAG_VOCAB_VERSION = 3


# ─── Full mechanic catalog ────────────────────────────────────────────────────
# Mirrors the printed keyword vocabulary of Magic so the chip picker's "All
# mechanics" tab can surface every card that mentions a given mechanic by
# name. Distinct from the curated archetype taggers below: those infer
# deck-level archetypes (aristocrats, voltron, mill, etc.); these tags are
# literal keyword presence. The frontend mirror lives in
# ``frontend/lib/mechanics.ts`` — both must stay in sync.
_FULL_MECHANIC_PATTERNS: dict[str, re.Pattern[str]] = {
    # Evergreen combat keywords
    "flying": _re(r"\bflying\b"),
    "first_strike": _re(r"\bfirst strike\b"),
    "double_strike": _re(r"\bdouble strike\b"),
    "deathtouch": _re(r"\bdeathtouch\b"),
    "hexproof": _re(r"\bhexproof\b"),
    "indestructible": _re(r"\bindestructible\b"),
    "lifelink": _re(r"\blifelink\b"),
    "menace": _re(r"\bmenace\b"),
    "reach": _re(r"\breach\b"),
    "trample": _re(r"\btrample\b"),
    "vigilance": _re(r"\bvigilance\b"),
    "ward": _re(r"\bward\b"),
    "defender": _re(r"\bdefender\b"),
    "flash": _re(r"\bflash\b"),
    "haste": _re(r"\bhaste\b"),
    "shroud": _re(r"\bshroud\b"),
    # Combat / pumping
    "annihilator": _re(r"\bannihilator\b"),
    "battle_cry": _re(r"\bbattle cry\b"),
    "exalted": _re(r"\bexalted\b"),
    "frenzy": _re(r"\bfrenzy\b"),
    "rampage": _re(r"\brampage\b"),
    "soulbond": _re(r"\bsoulbond\b"),
    "undying": _re(r"\bundying\b"),
    "persist": _re(r"\bpersist\b"),
    "mentor": _re(r"\bmentor\b"),
    "renown": _re(r"\brenown\b"),
    "training_kw": _re(r"\btraining\b"),
    # Graveyard / recursion
    "dredge": _re(r"\bdredge\b"),
    "scavenge": _re(r"\bscavenge\b"),
    "unearth": _re(r"\bunearth\b"),
    "embalm": _re(r"\bembalm\b"),
    "eternalize": _re(r"\beternalize\b"),
    "encore": _re(r"\bencore\b"),
    "threshold": _re(r"\bthreshold\b"),
    "delirium": _re(r"\bdelirium\b"),
    "morbid": _re(r"\bmorbid\b"),
    "flashback": _re(r"\bflashback\b"),
    "escape": _re(r"\bescape\b"),
    "jump_start": _re(r"\bjump-?start\b"),
    "disturb": _re(r"\bdisturb\b"),
    "madness": _re(r"\bmadness\b"),
    "retrace": _re(r"\bretrace\b"),
    # Cost / cast mechanics
    "cycling": _re(r"\bcycling\b"),
    "buyback": _re(r"\bbuyback\b"),
    "kicker": _re(r"\bkicker\b|\bmultikicker\b"),
    "suspend": _re(r"\bsuspend\b"),
    "convoke": _re(r"\bconvoke\b"),
    "delve": _re(r"\bdelve\b"),
    "improvise": _re(r"\bimprovise\b"),
    "affinity": _re(r"\baffinity for\b"),
    "rebound": _re(r"\brebound\b"),
    "miracle": _re(r"\bmiracle\b"),
    "foretell": _re(r"\bforetell\b"),
    "overload": _re(r"\boverload\b"),
    "splice": _re(r"\bsplice\b"),
    "transmute": _re(r"\btransmute\b"),
    "prototype": _re(r"\bprototype\b"),
    "casualty": _re(r"\bcasualty\b"),
    "mutate": _re(r"\bmutate\b"),
    "emerge": _re(r"\bemerge\b"),
    "bestow": _re(r"\bbestow\b"),
    "awaken": _re(r"\bawaken\b"),
    "spree": _re(r"\bspree\b"),
    "disguise": _re(r"\bdisguise\b"),
    "cloak": _re(r"\bcloak\b"),
    "bargain": _re(r"\bbargain\b"),
    "plot": _re(r"\bplot\b"),
    "saddle": _re(r"\bsaddle\b"),
    "surge": _re(r"\bsurge\b"),
    # Counters / power-toughness mechanics
    "modular": _re(r"\bmodular\b"),
    "devour": _re(r"\bdevour\b"),
    "monstrosity": _re(r"\bmonstrosity\b|\bmonstrous\b"),
    "outlast": _re(r"\boutlast\b"),
    "fabricate": _re(r"\bfabricate\b"),
    "adapt": _re(r"\badapt\b"),
    "evolve": _re(r"\bevolve\b"),
    "support": _re(r"\bsupport \d"),
    "level_up": _re(r"\blevel up\b"),
    "bolster": _re(r"\bbolster\b"),
    "reinforce": _re(r"\breinforce\b"),
    "explore": _re(r"\bexplore(?:s|d|ing)?\b"),
    "discover": _re(r"\bdiscover(?: \d|ed|ing|s)?\b"),
    "amass": _re(r"\bamass\b"),
    # Triggers / states / locations
    "raid": _re(r"\braid\b"),
    "revolt": _re(r"\brevolt\b"),
    "metalcraft": _re(r"\bmetalcraft\b"),
    "ferocious": _re(r"\bferocious\b"),
    "formidable": _re(r"\bformidable\b"),
    "hellbent": _re(r"\bhellbent\b"),
    "spell_mastery": _re(r"\bspell mastery\b"),
    "constellation": _re(r"\bconstellation\b"),
    "magecraft": _re(r"\bmagecraft\b"),
    "undergrowth": _re(r"\bundergrowth\b"),
    "monarch": _re(r"\bthe monarch\b"),
    "initiative": _re(r"\bthe initiative\b"),
    "dungeon": _re(r"\bventure into\b|\bcomplete(?:d|s)? (?:a |the )?dungeon"),
    "the_ring": _re(r"\bthe ring tempts you\b"),
    "addendum": _re(r"\baddendum\b"),
    "coven": _re(r"\bcoven\b"),
    "inspired": _re(r"\binspired\b"),
    "heroic": _re(r"\bheroic\b"),
    "domain": _re(r"\bdomain\b"),
    "descend": _re(r"\bdescend\b"),
    "eerie": _re(r"\beerie\b"),
    "celebration": _re(r"\bcelebration\b"),
    "party": _re(r"\b(?:full )?party\b"),
    "manifest": _re(r"\bmanifest\b"),
    "populate": _re(r"\bpopulate\b"),
    "changeling": _re(r"\bchangeling\b"),
}


def _tag_full_mechanics(text: str, tags: list[str]) -> None:
    """Append a tag for every printed mechanic the oracle text mentions.

    Additive over the curated archetype taggers — duplicates are skipped. The
    catalog is intentionally permissive: a card with `flying` ends up under the
    Flying chip even though Flying isn't a deck archetype on its own. That's
    the point of the "All mechanics" tab.
    """
    existing = set(tags)
    for tag, pat in _FULL_MECHANIC_PATTERNS.items():
        if tag in existing:
            continue
        if pat.search(text):
            tags.append(tag)
            existing.add(tag)


def _tribal_pattern(subtype: str) -> re.Pattern[str]:
    """Match oracle text that scopes an effect to a creature subtype."""
    s = re.escape(subtype)
    return re.compile(
        rf"\b(?:each|every|other|another|all|target)\s+{s}s?\b"
        rf"|\b{s}s?\s+you\s+(?:control|own)\b"
        rf"|\b{s}\s+spells\s+you\s+cast\b"
        rf"|\b{s}\s+creatures?\s+you\s+control\b",
        re.IGNORECASE,
    )


_TRIBAL_PATTERNS: dict[str, re.Pattern[str]] = {s: _tribal_pattern(s) for s in _TRIBAL_SUBTYPES}


def classify_tribal(oracle_text: str | None) -> list[str]:
    """Emit `<subtype>_tribal` tags for any tribe the card's text scopes to.

    Distinct from cards that merely *are* the subtype — only fires when the
    oracle text explicitly cares about other members of the tribe (e.g.
    "other Squirrels you control get +1/+1").

    Args:
        oracle_text: Rules text of the card.

    Returns:
        List of `<lowercase_subtype>_tribal` tags (may be empty).
    """
    text = oracle_text or ""
    if not text:
        return []
    return [f"{name.lower()}_tribal" for name, pat in _TRIBAL_PATTERNS.items() if pat.search(text)]


# Token type patterns — specific token names adjacent to "token" in oracle text
_TOKEN_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "treasure": _re(r"\btreasure token"),
    "food": _re(r"\bfood token"),
    "clue": _re(r"\bclue token"),
    "blood": _re(r"\bblood token"),
    "powerstone": _re(r"\bpowerstone token"),
    "map": _re(r"\bmap token"),
    "incubator": _re(r"\bincubator token"),
    # Creature token types
    "zombie": _re(r"\bZombie[\w\s,/]*token"),
    "soldier": _re(r"\bSoldier[\w\s,/]*token"),
    "spirit": _re(r"\bSpirit[\w\s,/]*token"),
    "saproling": _re(r"\bSaproling[\w\s,/]*token"),
    "goblin": _re(r"\bGoblin[\w\s,/]*token"),
    "elf": _re(r"\bElf[\w\s,/]*token"),
    "squirrel": _re(r"\bSquirrel[\w\s,/]*token"),
    "angel": _re(r"\bAngel[\w\s,/]*token"),
    "demon": _re(r"\bDemon[\w\s,/]*token"),
    "dragon": _re(r"\bDragon[\w\s,/]*token"),
    "elemental": _re(r"\bElemental[\w\s,/]*token"),
    "beast": _re(r"\bBeast[\w\s,/]*token"),
    "bird": _re(r"\bBird[\w\s,/]*token"),
    "cat": _re(r"\bCat[\w\s,/]*token"),
    "human": _re(r"\bHuman[\w\s,/]*token"),
    "knight": _re(r"\bKnight[\w\s,/]*token"),
    "warrior": _re(r"\bWarrior[\w\s,/]*token"),
    "thopter": _re(r"\bThopter[\w\s,/]*token"),
    "servo": _re(r"\bServo[\w\s,/]*token"),
    "insect": _re(r"\bInsect[\w\s,/]*token"),
    "rat": _re(r"\bRat[\w\s,/]*token"),
    "snake": _re(r"\bSnake[\w\s,/]*token"),
    "wolf": _re(r"\bWolf[\w\s,/]*token"),
    "vampire": _re(r"\bVampire[\w\s,/]*token"),
    "faerie": _re(r"\bFaerie[\w\s,/]*token"),
    "merfolk": _re(r"\bMerfolk[\w\s,/]*token"),
    "plant": _re(r"\bPlant[\w\s,/]*token"),
    "horror": _re(r"\bHorror[\w\s,/]*token"),
}

# Trait patterns — mechanical playstyle categories not covered by tags/types
_PAT_ETB = _re(r"when [\w\s,'/~]+ enters(?: the battlefield)?|enters the battlefield")
_PAT_ACTIVATED = _re(r"\{[^{}]+\}[^.!?\n]*:")
_PAT_CANT_BE_BLOCKED = _re(r"can't be blocked")

# Evasion keywords from Scryfall (lowercased for set intersection)
_EVASION_KEYWORDS = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "shadow",
        "fear",
        "intimidate",
        "skulk",
        "horsemanship",
    }
)


def classify_traits(
    oracle_text: str | None,
    keywords: list[str],
) -> list[str]:
    """Classify mechanical traits from oracle text and keyword abilities.

    Args:
        oracle_text: Rules text of the card.
        keywords: Scryfall keyword abilities list.

    Returns:
        List of trait strings (may be empty).
    """
    text = oracle_text or ""
    kw_set = {k.lower() for k in keywords}
    traits: list[str] = []
    if _PAT_ETB.search(text):
        traits.append("etb")
    if _PAT_ACTIVATED.search(text):
        traits.append("activated")
    if kw_set & _EVASION_KEYWORDS or _PAT_CANT_BE_BLOCKED.search(text):
        traits.append("evasion")
    return traits


def classify_token_types(oracle_text: str | None) -> list[str]:
    """Classify which specific token types a card produces from oracle text.

    Args:
        oracle_text: Rules text of the card.

    Returns:
        List of token type strings matching the supported set (may be empty).
    """
    text = oracle_text or ""
    return [name for name, pat in _TOKEN_TYPE_PATTERNS.items() if pat.search(text)]


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


def _tag_graveyard_sacrifice(text: str, kw_set: set[str], tags: list[str]) -> None:
    if _PAT_PLUS_ONE.search(text):
        tags.append("plus_one_counters")
    if _PAT_LIFEGAIN.search(text) or "lifelink" in kw_set:
        tags.append("lifegain")
    # Hate first so we don't double-tag with the recursion bucket.
    is_hate = bool(_PAT_GRAVEYARD_HATE.search(text))
    if is_hate:
        tags.append("graveyard_hate")
    if not is_hate and _PAT_GRAVEYARD.search(text):
        tags.append("graveyard")
    has_sacrifice = bool(_PAT_SACRIFICE.search(text))
    has_death = bool(_PAT_DEATH_TRIGGER.search(text))
    if has_sacrifice:
        tags.append("sacrifice")
    if has_sacrifice and has_death:
        tags.append("aristocrats")


def _tag_extras(text: str, kw_set: set[str], tags: list[str]) -> None:
    """Misc tags that fire from a single regex/keyword check apiece."""
    if _PAT_COST_REDUCTION.search(text):
        tags.append("cost_reduction")
    if _PAT_ANTHEM.search(text):
        tags.append("anthem")
    if "proliferate" in kw_set or re.search(r"\bproliferate\b", text, re.IGNORECASE):
        tags.append("proliferate")
    if _PAT_CARD_SELECTION.search(text) or kw_set & {
        "scry",
        "surveil",
        "explore",
        "discover",
        "investigate",
    }:
        tags.append("card_selection")


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
    if _PAT_ENERGY.search(text):
        tags.append("energy")


def _tag_keyword_archetypes(text: str, kw_set: set[str], tags: list[str]) -> None:
    """Archetype tags that key off Scryfall keyword abilities or simple patterns."""
    if _PAT_REANIMATOR.search(text):
        tags.append("reanimator")
    if "cascade" in kw_set or _PAT_CASCADE.search(text):
        tags.append("cascade")
    if "storm" in kw_set or _PAT_STORM.search(text):
        tags.append("storm")
    if "landfall" in kw_set or _PAT_LANDFALL.search(text):
        tags.append("landfall")
    if "infect" in kw_set or "toxic" in kw_set or _PAT_INFECT_TOXIC.search(text):
        tags.append("infect_toxic")


def _tag_token_economies(text: str, tags: list[str]) -> None:
    """Cares-about tags for the common token-as-resource archetypes."""
    if _PAT_TREASURE_CARES.search(text):
        tags.append("treasure_matters")
    if _PAT_FOOD_CARES.search(text):
        tags.append("food_matters")
    if _PAT_CLUE_CARES.search(text):
        tags.append("clue_matters")


def _tag_spell_archetypes(text: str, tags: list[str]) -> None:
    """Spellslinger / wheels triggers."""
    if _PAT_SPELLSLINGER.search(text):
        tags.append("spellslinger")
    if _PAT_WHEELS.search(text):
        tags.append("wheels")


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
    _tag_graveyard_sacrifice(text, kw_set, tags)
    _tag_equipment_voltron(tl, text, tags)
    _tag_stax_hug_mana(name, text, cmc, tags)
    _tag_protection_misc(text, tl, kw_set, tags)
    _tag_extras(text, kw_set, tags)
    _tag_keyword_archetypes(text, kw_set, tags)
    _tag_token_economies(text, tags)
    _tag_spell_archetypes(text, tags)
    _tag_full_mechanics(text, tags)
    tags.extend(classify_tribal(oracle_text))

    return tags


async def _sync_tags_to_qdrant(pool: asyncpg.Pool, qdrant_client: AsyncQdrantClient) -> None:
    """Push updated tags and traits from Postgres into Qdrant point payloads.

    Uses concurrent set_payload calls in batches to avoid 30k sequential
    round-trips.

    Args:
        pool: asyncpg connection pool.
        qdrant_client: Async Qdrant client.
    """
    from mtg_helper.config import settings

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, tags, traits, token_types FROM cards WHERE embedded_at IS NOT NULL"
        )

    _log.info("Syncing %d card tags/traits to Qdrant", len(rows))

    async def _update_one(
        card_id: Any, tags: list[str], traits: list[str], token_types: list[str]
    ) -> None:
        await qdrant_client.set_payload(
            collection_name=settings.qdrant_collection,
            payload={"tags": tags, "traits": traits, "token_types": token_types},
            points=[str(card_id)],
        )

    for i in range(0, len(rows), _QDRANT_CONCURRENCY):
        chunk = rows[i : i + _QDRANT_CONCURRENCY]
        await asyncio.gather(
            *[
                _update_one(r["id"], list(r["tags"]), list(r["traits"]), list(r["token_types"]))
                for r in chunk
            ]
        )


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
        updates: list[tuple[list[str], list[str], list[str], Any]] = [
            (
                classify_card(
                    r["name"],
                    r["type_line"],
                    r["oracle_text"],
                    list(r["keywords"]),
                    float(r["cmc"]) if r["cmc"] is not None else None,
                ),
                classify_traits(r["oracle_text"], list(r["keywords"])),
                classify_token_types(r["oracle_text"]),
                r["id"],
            )
            for r in batch
        ]

        async with pool.acquire() as conn:
            await conn.executemany(
                "UPDATE cards SET tags = $1, traits = $2, token_types = $3 WHERE id = $4",
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

"""Bracket rule validation for a deck.

Compares a deck's cards (and active combos) against WotC's Commander
Bracket criteria — Game Changers, mass land destruction, fast mana, and
two-card infinite combos — and reports per-rule violations.

Bracket policy used here (Brackets 1–4):
    1 (Casual):    no Game Changers, no MLD, no fast mana, no 2-card infinites
    2 (Upgraded):  no Game Changers, no MLD, no 2-card infinites
    3 (Optimized): up to 3 Game Changers, no MLD
    4 (cEDH):     anything allowed
"""

from mtg_helper.models.brackets import BracketValidationResponse, BracketViolation
from mtg_helper.models.combos import ComboListResponse
from mtg_helper.models.decks import DeckDetailResponse

# Curated WotC "Game Changers" list (Commander Bracket System). Names are
# matched case-insensitively against the deck's card list and the commander.
GAME_CHANGERS: frozenset[str] = frozenset(
    {
        "Ancient Tomb",
        "Bolas's Citadel",
        "Chrome Mox",
        "Coalition Victory",
        "Cyclonic Rift",
        "Demonic Tutor",
        "Dockside Extortionist",
        "Drannith Magistrate",
        "Enlightened Tutor",
        "Field of the Dead",
        "Gaea's Cradle",
        "Glacial Chasm",
        "Grim Monolith",
        "Imperial Seal",
        "Jeweled Lotus",
        "Kinnan, Bonder Prodigy",
        "Lion's Eye Diamond",
        "Mana Crypt",
        "Mana Vault",
        "Mox Diamond",
        "Mox Opal",
        "Mystical Tutor",
        "Opposition Agent",
        "Ragavan, Nimble Pilferer",
        "Rhystic Study",
        "Serra's Sanctum",
        "Smothering Tithe",
        "Tergrid, God of Fright",
        "Thassa's Oracle",
        "The One Ring",
        "The Tabernacle at Pendrell Vale",
        "Trouble in Pairs",
        "Underworld Breach",
        "Vampiric Tutor",
        "Winota, Joiner of Forces",
        "Yuriko, the Tiger's Shadow",
    }
)

# Mass land destruction — board wipes of lands and similar effects.
MASS_LAND_DESTRUCTION: frozenset[str] = frozenset(
    {
        "Armageddon",
        "Ravages of War",
        "Catastrophe",
        "Decree of Annihilation",
        "Obliterate",
        "Jokulhaups",
        "Wildfire",
        "Devastation",
        "Cataclysm",
        "Worldfire",
        "Apocalypse",
        "Boom // Bust",
        "Sunder",
        "Impending Disaster",
        "Epicenter",
        "Tectonic Break",
        "Magus of the Disk",
        "Nevinyrral's Disk",
    }
)

# Fast mana — sub-CMC-2 rocks/rituals/lands that produce more mana than they cost.
# Sol Ring is intentionally allowed (it is on the precon list).
FAST_MANA: frozenset[str] = frozenset(
    {
        "Mana Crypt",
        "Mana Vault",
        "Mox Diamond",
        "Mox Opal",
        "Chrome Mox",
        "Jeweled Lotus",
        "Lion's Eye Diamond",
        "Grim Monolith",
        "Lotus Petal",
        "Ancient Tomb",
        "Dark Ritual",
        "Cabal Ritual",
        "Rite of Flame",
        "Pyretic Ritual",
        "Desperate Ritual",
    }
)


def _normalize_names(deck: DeckDetailResponse) -> dict[str, str]:
    """Return ``lower(name) -> name`` for every card on the deck (and commanders)."""
    out: dict[str, str] = {}
    for card in deck.cards:
        if card.name:
            out[card.name.lower()] = card.name
    if deck.commander_card and deck.commander_card.name:
        out[deck.commander_card.name.lower()] = deck.commander_card.name
    if deck.partner_card and deck.partner_card.name:
        out[deck.partner_card.name.lower()] = deck.partner_card.name
    return out


def _match(names_in_deck: dict[str, str], catalog: frozenset[str]) -> list[str]:
    """Return display names from the deck that appear in ``catalog`` (case-insensitive)."""
    lowered = {n.lower() for n in catalog}
    return sorted({names_in_deck[k] for k in names_in_deck if k in lowered})


def _two_card_active_combos(combos: ComboListResponse | None) -> list[list[str]]:
    """Active combos with exactly two pieces and all pieces in the deck."""
    if combos is None:
        return []
    result: list[list[str]] = []
    for combo in combos.active:
        if combo.missing_count != 0:
            continue
        if len(combo.pieces) != 2:
            continue
        if not all(p.in_deck for p in combo.pieces):
            continue
        result.append([p.card.name for p in combo.pieces])
    return result


def _check_game_changers(hits: list[str], declared: int) -> BracketViolation | None:
    """Game Changers: blocked at 1/2, capped at 3 in bracket 3."""
    if not hits:
        return None
    if declared <= 2:
        return BracketViolation(
            rule="game_changer",
            severity="block",
            message=f"Bracket {declared} disallows Game Changers; found {len(hits)}.",
            cards=hits,
        )
    if declared == 3 and len(hits) > 3:
        return BracketViolation(
            rule="game_changer",
            severity="block",
            message=f"Bracket 3 allows at most 3 Game Changers; found {len(hits)}.",
            cards=hits,
        )
    return None


def _check_mld(hits: list[str], declared: int) -> BracketViolation | None:
    """Mass land destruction: blocked at brackets 1, 2, and 3."""
    if not hits or declared > 3:
        return None
    return BracketViolation(
        rule="mass_land_destruction",
        severity="block",
        message=f"Bracket {declared} disallows mass land destruction.",
        cards=hits,
    )


def _check_fast_mana(hits: list[str], declared: int) -> BracketViolation | None:
    """Fast mana: blocked only at bracket 1 (Sol Ring excluded above)."""
    if not hits or declared != 1:
        return None
    return BracketViolation(
        rule="fast_mana",
        severity="block",
        message="Bracket 1 disallows fast mana.",
        cards=hits,
    )


def _check_infinite_combos(pairs: list[list[str]], declared: int) -> BracketViolation | None:
    """Two-card infinite combos: blocked at 1 and 2; warn at 3."""
    if not pairs:
        return None
    flat = sorted({name for pair in pairs for name in pair})
    if declared <= 2:
        return BracketViolation(
            rule="infinite_combo",
            severity="block",
            message=(f"Bracket {declared} disallows two-card infinite combos; found {len(pairs)}."),
            cards=flat,
        )
    if declared == 3:
        return BracketViolation(
            rule="infinite_combo",
            severity="warn",
            message="Bracket 3 discourages early two-card infinite combos.",
            cards=flat,
        )
    return None


def validate_bracket(
    deck: DeckDetailResponse,
    combos: ComboListResponse | None,
) -> BracketValidationResponse:
    """Validate a deck against its declared bracket.

    Args:
        deck: Full deck detail including commander.
        combos: Optional combo list from Commander Spellbook; when omitted,
            combo-based rules are skipped.

    Returns:
        BracketValidationResponse with the declared bracket, a ``legal``
        flag (no blocking violations), and a list of violations.
    """
    declared = deck.bracket or 3
    names_in_deck = _normalize_names(deck)

    candidates = [
        _check_game_changers(_match(names_in_deck, GAME_CHANGERS), declared),
        _check_mld(_match(names_in_deck, MASS_LAND_DESTRUCTION), declared),
        _check_fast_mana(_match(names_in_deck, FAST_MANA), declared),
        _check_infinite_combos(_two_card_active_combos(combos), declared),
    ]
    violations = [v for v in candidates if v is not None]
    legal = not any(v.severity == "block" for v in violations)
    return BracketValidationResponse(
        declared_bracket=declared,
        legal=legal,
        violations=violations,
    )

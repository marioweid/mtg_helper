"""Deckbuilder role derivation from canonical card facts.

Builder roles are not theme tags. They are deck-construction counters derived
from Moxfield hub/local/MTGJSON tags and card type, with deck-local manual overrides
handled separately on ``deck_cards.categories``.
"""

from dataclasses import dataclass, field

_ROLE_ORDER = ("ramp", "draw", "interaction", "lands")

_ROLE_TAGS: dict[str, frozenset[str]] = {
    "ramp": frozenset(
        {
            "ramp",
            "fast_mana",
            "cost_reduction",
            "treasure",
            "treasures",
            "treasure_matters",
            "mana_rock",
            "mana_dork",
            "mana",
        }
    ),
    "draw": frozenset(
        {
            "draw",
            "card_draw",
            "card_advantage",
            "card_selection",
            "cantrip",
            "wheels",
            "wheel",
            "cycling",
            "investigate",
            "clue",
            "clues",
            "curiosity",
            "looting",
            "impulse_draw",
        }
    ),
    "interaction": frozenset(
        {
            "interaction",
            "removal",
            "board_wipe",
            "counterspell",
            "counter",
            "protection",
            "control",
            "stax",
            "graveyard_hate",
            "land_destruction",
            "bounce",
            "discard",
        }
    ),
}


@dataclass(frozen=True)
class BuilderRoles:
    """Derived deckbuilder roles plus the tags that explain each role."""

    roles: list[str]
    reasons: dict[str, list[str]] = field(default_factory=dict)


def derive_builder_roles(
    hub_tags: list[str],
    mtgjson_tags: list[str],
    type_line: str | None,
) -> BuilderRoles:
    """Derive builder role counters from card facts.

    Args:
        hub_tags: Moxfield hub tags or local rule tags stored on the card.
        mtgjson_tags: MTGJSON keyword/mechanic tags stored on the card.
        type_line: Card type line, used for land detection.

    Returns:
        Roles in stable display order and per-role source tags.
    """
    tag_set = {tag for tag in [*hub_tags, *mtgjson_tags] if tag}
    reasons: dict[str, list[str]] = {}

    if "Land" in (type_line or ""):
        return BuilderRoles(roles=["lands"], reasons={"lands": ["type: land"]})

    for role, role_tags in _ROLE_TAGS.items():
        matched = sorted(tag_set & role_tags)
        if matched:
            reasons[role] = matched

    roles = [role for role in _ROLE_ORDER if role in reasons]
    return BuilderRoles(roles=roles, reasons={role: reasons[role] for role in roles})

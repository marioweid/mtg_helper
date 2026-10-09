"""Pure source identity and eligibility contracts shared with offline evaluations."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

Card = dict[str, Any]
_EXCLUDED_LAYOUTS = {"token", "double_faced_token", "art_series", "emblem", "planar", "scheme"}


@dataclass
class Catalog:
    """Source identities indexed without back-face name collisions."""

    exact: dict[str, dict[str, Card]]
    fronts: dict[str, dict[str, Card]]

    def resolve(self, name: str) -> Card | None:
        matches = self.exact.get(name.casefold()) or self.fronts.get(name.casefold(), {})
        return next(iter(matches.values())) if len(matches) == 1 else None


def paper_design(card: Card) -> bool:
    """Identify plausible paper gameplay objects, not certify future legality."""
    return bool(
        "paper" in card.get("games", [])
        and card.get("oracle_id")
        and card.get("layout") not in _EXCLUDED_LAYOUTS
        and card.get("border_color") not in {"silver", "gold"}
        and card.get("security_stamp") != "acorn"
        and card.get("set_type") not in {"memorabilia", "token", "vanguard"}
    )


def build_catalog(cards: Iterable[Card]) -> Catalog:
    """Index eligible paper identities, resolving complete names before front aliases."""
    catalog = Catalog({}, {})
    for card in cards:
        if not paper_design(card):
            continue
        catalog.exact.setdefault(card["name"].casefold(), {})[card["oracle_id"]] = card
        if card.get("card_faces"):
            name = card["card_faces"][0]["name"].casefold()
            catalog.fronts.setdefault(name, {})[card["oracle_id"]] = card
    return catalog


def is_land(card: Card) -> bool:
    faces = card.get("card_faces") or []
    return "Land" in (faces[0]["type_line"] if faces else card["type_line"])


def eligibility_error(card: Card | None, colors: set[str], commander_id: str) -> str | None:
    """Check mechanical eligibility only, not strategic quality or interpretation of rules."""
    if card is None:
        return "unresolved_or_ambiguous"
    if card["oracle_id"] == commander_id:
        return "commander"
    if card["legalities"].get("commander") != "legal":
        return "not_commander_legal"
    if not set(card["color_identity"]) <= colors:
        return "off_color"
    return "land" if is_land(card) else None

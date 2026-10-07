"""Conservative printing-history normalization; never infer preview playability."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from mtg_helper.models.new_cards import CardFacts, NewCardFace

REGULAR_PRODUCTS = {"core", "expansion", "masters", "commander", "draft_innovation"}
EXCLUDED_LAYOUTS = {
    "token",
    "double_faced_token",
    "emblem",
    "art_series",
    "planar",
    "scheme",
    "vanguard",
    "augment",
    "host",
}


def paper_card(card: dict[str, Any]) -> bool:
    """Accept physical gameplay shapes, independently of current format legality."""
    return bool(
        card.get("oracle_id")
        and "paper" in card.get("games", [])
        and card.get("layout") not in EXCLUDED_LAYOUTS
        and card.get("border_color") not in {"silver", "gold"}
        and card.get("security_stamp") != "acorn"
        and card.get("set_type") not in {"memorabilia", "token", "vanguard"}
        and "Conspiracy" not in (card.get("type_line") or "")
    )


@dataclass(slots=True)
class ReleaseHistory:
    """Keep earliest paper, nonpromo and demonstrably original regular releases separate."""

    first_paper: date | None = None
    first_nonpromo: date | None = None
    first_regular: date | None = None
    original_regular: date | None = None
    uncertain: bool = False

    def observe(self, card: dict[str, Any]) -> None:
        raw_date = card.get("released_at")
        if not raw_date:
            self.uncertain = True
            return
        released = date.fromisoformat(raw_date)
        self.first_paper = min(self.first_paper or released, released)
        if card.get("promo") or card.get("set_type") == "promo":
            return
        self.first_nonpromo = min(self.first_nonpromo or released, released)
        if card.get("set_type") not in REGULAR_PRODUCTS:
            return
        self.first_regular = min(self.first_regular or released, released)
        if card.get("reprint") is False:
            self.original_regular = min(self.original_regular or released, released)

    @property
    def release(self) -> date | None:
        """Exclude ambiguous origins rather than relabel an old design as new."""
        if self.uncertain or self.original_regular != self.first_regular:
            return None
        if self.first_nonpromo != self.first_regular:
            return None
        return self.first_regular


def release_history(cards: Iterable[dict[str, Any]]) -> dict[str, ReleaseHistory]:
    """Reduce all printings by Oracle identity, without retaining the entire export."""
    result: dict[str, ReleaseHistory] = {}
    for card in cards:
        if paper_card(card):
            result.setdefault(card["oracle_id"], ReleaseHistory()).observe(card)
    return result


def card_facts(card: dict[str, Any]) -> CardFacts:
    """Preserve source fields and face access boundaries; no generated characteristics."""
    faces = [NewCardFace.model_validate(face) for face in card.get("card_faces", [])]
    text = card.get("oracle_text") or ""
    if faces:
        text = "\n".join(f"{face.name} [{face.type_line}]: {face.oracle_text}" for face in faces)
    return CardFacts.model_validate(
        {
            **{field: card.get(field) for field in NewCardFace.model_fields},
            "oracle_text": text,
            "oracle_id": card["oracle_id"],
            "color_identity": card.get("color_identity") or [],
            "commander_legality": (card.get("legalities") or {}).get("commander", "not_legal"),
            "layout": card.get("layout", "normal"),
            "faces": faces,
            "game_changer": bool(card.get("game_changer")),
        }
    )

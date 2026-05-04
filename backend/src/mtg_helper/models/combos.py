"""Pydantic models for the deck-combo discovery endpoint."""

from uuid import UUID

from pydantic import BaseModel


class ComboCardRef(BaseModel):
    """A card referenced by a Commander Spellbook combo entry.

    ``scryfall_id`` and ``image_uri`` are populated when the card is in our
    local Scryfall cache; otherwise the UI renders a name-only chip.
    """

    name: str
    scryfall_id: UUID | None = None
    image_uri: str | None = None


class ComboPiece(BaseModel):
    """One required card of a combo, paired with its in-deck status."""

    card: ComboCardRef
    in_deck: bool


class Combo(BaseModel):
    """A combo from Commander Spellbook, trimmed to the fields the UI uses."""

    id: str
    pieces: list[ComboPiece]
    produces: list[str]
    description: str | None = None
    popularity: int | None = None
    bracket_tag: str | None = None
    missing_count: int


class ComboListResponse(BaseModel):
    """Combos relevant to a deck, split by missing-piece count."""

    active: list[Combo]
    almost_there: list[Combo]

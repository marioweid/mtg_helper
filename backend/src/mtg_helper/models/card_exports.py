"""Read-only card export requests and binder-aware previews."""

from uuid import UUID

from pydantic import BaseModel, Field

from mtg_helper.models.ai import CollectionMembership


class ExportCard(BaseModel):
    card_id: UUID
    quantity: int = Field(ge=1, le=10000, strict=True)


class CardExportRequest(BaseModel):
    cards: list[ExportCard] = Field(max_length=1000)
    collection_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class CardExportRow(BaseModel):
    card_id: UUID
    name: str
    needed_quantity: int
    available_quantity: int
    export_quantity: int
    price_eur_cents: int | None
    pulls: list[CollectionMembership] = Field(default_factory=list)


class CardExportPreview(BaseModel):
    rows: list[CardExportRow]
    needed_quantity: int
    from_binders_quantity: int
    export_quantity: int
    known_price_eur_cents: int
    unpriced_quantity: int
    text: str

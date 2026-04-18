"""Pydantic models for collection requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CollectionCreate(BaseModel):
    """Request body for creating a new collection."""

    name: str = Field(min_length=1, max_length=200)


class CollectionUpdate(BaseModel):
    """Request body for renaming a collection."""

    name: str = Field(min_length=1, max_length=200)


class CollectionResponse(BaseModel):
    """Collection metadata with aggregate card count."""

    id: UUID
    account_id: UUID
    name: str
    card_count: int
    created_at: datetime


class CollectionCardItem(BaseModel):
    """A single printing entry in a collection, enriched with card data."""

    card_id: UUID
    scryfall_id: UUID
    name: str
    set_code: str
    collector_number: str
    image_uri: str | None
    color_identity: list[str]
    type_line: str | None
    quantity: int
    foil: bool
    condition: str | None
    language: str | None
    tags: list[str]
    purchase_price: Decimal | None
    last_modified: datetime | None


class CollectionCardAdd(BaseModel):
    """Request body for adding a single card to a collection (search-bar flow).

    Provide exactly one of ``scryfall_id`` (preferred) or ``name``. When ``name``
    is provided, the service resolves it via fuzzy card-name matching.
    """

    scryfall_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)
    foil: bool = False
    set_code: str = ""
    collector_number: str = ""
    condition: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    purchase_price: Decimal | None = None

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "CollectionCardAdd":
        if (self.scryfall_id is None) == (self.name is None):
            raise ValueError("Provide exactly one of 'scryfall_id' or 'name'.")
        return self


class CollectionCardUpdate(BaseModel):
    """Request body for patching a collection card row. All fields optional."""

    quantity: int | None = Field(default=None, ge=1)
    condition: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    purchase_price: Decimal | None = None


class CollectionImportRequest(BaseModel):
    """Request body for importing a Moxfield CSV."""

    csv: str = Field(min_length=1, max_length=10_000_000)
    mode: Literal["merge", "replace"] = "merge"


class CollectionImportResponse(BaseModel):
    """Result of a CSV import: counts plus unresolved and ambiguous rows."""

    imported: int
    updated: int
    removed: int
    unresolved: list[str]

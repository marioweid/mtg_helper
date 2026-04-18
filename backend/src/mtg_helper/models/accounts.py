"""Pydantic models for account requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    """Request body for creating a new account."""

    display_name: str = Field(min_length=1, max_length=100)


class AccountUpdate(BaseModel):
    """Request body for PATCH /accounts/{id}. All fields optional."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    collection_suggestions_enabled: bool | None = None
    default_collection_id: UUID | None = None
    collection_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class AccountResponse(BaseModel):
    """Account data returned from the API."""

    id: UUID
    display_name: str
    collection_suggestions_enabled: bool
    default_collection_id: UUID | None
    collection_threshold: float
    created_at: datetime

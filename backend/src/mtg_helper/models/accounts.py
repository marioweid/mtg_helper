"""Pydantic models for account requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    """Request body for creating a new account."""

    display_name: str = Field(min_length=1, max_length=100)


class AccountResponse(BaseModel):
    """Account data returned from the API."""

    id: UUID
    display_name: str
    created_at: datetime

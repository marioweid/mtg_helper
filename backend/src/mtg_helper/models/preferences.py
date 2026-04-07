"""Pydantic models for account preference requests and responses."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PreferenceCreate(BaseModel):
    """Request body for creating a preference."""

    preference_type: Literal[
        "pet_card",
        "avoid_card",
        "avoid_archetype",
        "general",
        "feedback_boosting",
        "user_profile_boosting",
    ]
    card_scryfall_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        """Enforce type-specific required fields."""
        if self.preference_type in ("pet_card", "avoid_card") and self.card_scryfall_id is None:
            raise ValueError(
                f"card_scryfall_id is required for preference_type={self.preference_type!r}"
            )
        if self.preference_type in ("avoid_archetype", "general") and not self.description:
            raise ValueError(
                f"description is required for preference_type={self.preference_type!r}"
            )
        return self


class PreferenceResponse(BaseModel):
    """Preference record returned from the API."""

    id: UUID
    account_id: UUID
    preference_type: str
    card_id: UUID | None
    card_name: str | None
    description: str | None
    created_at: datetime

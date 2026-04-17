"""Pydantic models for per-user ranking weight settings."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

_DEFAULT_SEMANTIC: float = 0.25
_DEFAULT_SYNERGY: float = 0.22
_DEFAULT_POPULARITY: float = 0.20
_DEFAULT_PERSONAL: float = 0.15


class RankingWeights(BaseModel):
    """Tunable signal weights for the hybrid retrieval scorer."""

    semantic: float = Field(default=_DEFAULT_SEMANTIC, ge=0.0, le=1.0)
    synergy: float = Field(default=_DEFAULT_SYNERGY, ge=0.0, le=1.0)
    popularity: float = Field(default=_DEFAULT_POPULARITY, ge=0.0, le=1.0)
    personal: float = Field(default=_DEFAULT_PERSONAL, ge=0.0, le=1.0)


class RankingWeightsResponse(RankingWeights):
    """Ranking weights with account metadata."""

    account_id: UUID
    updated_at: datetime


class RankingWeightsUpdate(BaseModel):
    """Request body for updating ranking weights."""

    semantic: float = Field(ge=0.0, le=1.0)
    synergy: float = Field(ge=0.0, le=1.0)
    popularity: float = Field(ge=0.0, le=1.0)
    personal: float = Field(ge=0.0, le=1.0)

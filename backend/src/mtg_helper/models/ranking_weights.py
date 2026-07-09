"""Pydantic models for per-user ranking weight settings."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

_DEFAULT_SEMANTIC: float = 0.25
_DEFAULT_SYNERGY: float = 0.22
_DEFAULT_POPULARITY: float = 0.10
_DEFAULT_PERSONAL: float = 0.15
_DEFAULT_DECK_INCLUSION: float = 0.20
_DEFAULT_MOXFIELD_INCLUSION: float = 0.20
# Fraction of each result page reserved for EDHREC/Moxfield trusted cards. The
# remainder is filled by composite (keyword + FTS) winners, giving
# user-supplied chips a real exploration channel. 1.0 keeps the historical
# "every trusted card first" behavior; 0.5 yields a 50/50 mix.
_DEFAULT_TRUSTED_QUOTA: float = 1.0


class RankingWeights(BaseModel):
    """Tunable signal weights for the structured retrieval scorer."""

    semantic: float = Field(default=_DEFAULT_SEMANTIC, ge=0.0, le=1.0)
    synergy: float = Field(default=_DEFAULT_SYNERGY, ge=0.0, le=1.0)
    popularity: float = Field(default=_DEFAULT_POPULARITY, ge=0.0, le=1.0)
    personal: float = Field(default=_DEFAULT_PERSONAL, ge=0.0, le=1.0)
    deck_inclusion: float = Field(default=_DEFAULT_DECK_INCLUSION, ge=0.0, le=1.0)
    moxfield_inclusion: float = Field(default=_DEFAULT_MOXFIELD_INCLUSION, ge=0.0, le=1.0)
    trusted_quota: float = Field(default=_DEFAULT_TRUSTED_QUOTA, ge=0.0, le=1.0)


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
    deck_inclusion: float = Field(ge=0.0, le=1.0)
    moxfield_inclusion: float = Field(ge=0.0, le=1.0)
    trusted_quota: float = Field(ge=0.0, le=1.0)

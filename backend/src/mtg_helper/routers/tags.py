"""Scryfall Oracle-tag and printed-keyword catalog endpoints."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mtg_helper.models.common import DataResponse

router = APIRouter(prefix="/tags", tags=["tags"])


class SourceTagChip(BaseModel):
    """A selectable source identity, never a locally invented label."""

    id: UUID
    slug: str
    label: str


class PrintedKeywordChip(BaseModel):
    """One exact printed Scryfall keyword."""

    keyword: str


@router.get("/oracle", response_model=DataResponse[list[SourceTagChip]])
async def list_oracle_tags(request: Request) -> DataResponse[list[SourceTagChip]]:
    """Return source Oracle tags from the current complete Scryfall publication."""
    rows = await request.app.state.db_pool.fetch(
        "SELECT id, slug, metadata->>'label' AS label FROM scryfall_tags ORDER BY slug"
    )
    return DataResponse(data=[SourceTagChip(**dict(row)) for row in rows])


@router.get("/keywords", response_model=DataResponse[list[PrintedKeywordChip]])
async def list_printed_keywords(request: Request) -> DataResponse[list[PrintedKeywordChip]]:
    """Return exact printed keywords from Scryfall card facts."""
    rows = await request.app.state.db_pool.fetch(
        "SELECT DISTINCT keyword FROM cards CROSS JOIN unnest(keywords) AS keyword "
        "WHERE is_canonical ORDER BY keyword"
    )
    return DataResponse(data=[PrintedKeywordChip(keyword=row["keyword"]) for row in rows])

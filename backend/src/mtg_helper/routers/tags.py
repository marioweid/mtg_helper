"""Tag catalog endpoints for EDHREC themes and MTGJSON mechanics."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mtg_helper.models.common import DataResponse
from mtg_helper.services import edhrec_tag_catalog_service

router = APIRouter(prefix="/tags", tags=["tags"])


class KeywordChip(BaseModel):
    """An official MTGJSON keyword exposed as a selectable tag chip."""

    tag: str
    label: str
    deck_count: int | None = None


class KeywordGroup(BaseModel):
    """Selectable tag group for the frontend picker."""

    category: str
    display_name: str
    keywords: list[KeywordChip]


_CATEGORY_LABELS = {
    "ability_word": "Ability words",
    "keyword_ability": "Keyword abilities",
    "keyword_action": "Keyword actions",
}


@router.get("/keywords", response_model=DataResponse[list[KeywordGroup]])
async def list_official_keywords(request: Request) -> DataResponse[list[KeywordGroup]]:
    """Return the locally synced MTGJSON official keyword catalog."""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, label, category
            FROM mtgjson_keywords
            ORDER BY category ASC, label ASC
            """
        )

    by_category: dict[str, list[KeywordChip]] = {key: [] for key in _CATEGORY_LABELS}
    for row in rows:
        category = row["category"]
        if category in by_category:
            by_category[category].append(KeywordChip(tag=row["tag"], label=row["label"]))
    return DataResponse(
        data=[
            KeywordGroup(
                category=category,
                display_name=label,
                keywords=by_category[category],
            )
            for category, label in _CATEGORY_LABELS.items()
            if by_category[category]
        ]
    )


@router.get("/edhrec", response_model=DataResponse[list[KeywordGroup]])
async def list_edhrec_tags(request: Request) -> DataResponse[list[KeywordGroup]]:
    """Return the locally synced EDHREC deckbuilding tag catalog."""
    pool = request.app.state.db_pool
    groups = await edhrec_tag_catalog_service.list_edhrec_tag_groups(pool)
    return DataResponse(data=[KeywordGroup(**group) for group in groups])

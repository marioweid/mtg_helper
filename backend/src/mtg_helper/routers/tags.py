"""MTGJSON keyword enumeration endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mtg_helper.models.common import DataResponse

router = APIRouter(prefix="/tags", tags=["tags"])


class KeywordChip(BaseModel):
    """An official MTGJSON keyword exposed as a selectable tag chip."""

    tag: str
    label: str


class KeywordGroup(BaseModel):
    """Official MTGJSON keyword group for the frontend picker."""

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

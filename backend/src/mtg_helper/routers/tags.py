"""Tag enumeration endpoints (used by the keyword pickers)."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from mtg_helper.models.common import DataResponse

router = APIRouter(prefix="/tags", tags=["tags"])


class TribalTag(BaseModel):
    """A tribal archetype with its corpus support count."""

    tag: str
    subtype: str
    card_count: int


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


@router.get("/tribal", response_model=DataResponse[list[TribalTag]])
async def list_tribal_tags(
    request: Request,
    min_count: int = Query(default=3, ge=1, le=1000),
) -> DataResponse[list[TribalTag]]:
    """Enumerate tribal mega-tags (`<subtype>_tribal`) with card support counts.

    The frontend keyword picker uses this to hide sparse tribes (e.g. obscure
    creature types with only 1–2 cares-about cards) and to drive autocomplete.

    Args:
        request: FastAPI request (for db pool access).
        min_count: Minimum number of cards that must carry the tribal tag for
            it to appear in the result. Defaults to 3.

    Returns:
        DataResponse listing each tribal tag, its display subtype, and the
        number of cards in the corpus carrying that tag, sorted by count desc.
    """
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tag, count(*)::int AS card_count
            FROM cards, unnest(tags) AS tag
            WHERE tag LIKE '%\\_tribal' ESCAPE '\\'
            GROUP BY tag
            HAVING count(*) >= $1
            ORDER BY card_count DESC, tag ASC
            """,
            min_count,
        )

    items = [
        TribalTag(
            tag=r["tag"],
            subtype=r["tag"].removesuffix("_tribal").replace("_", " ").title(),
            card_count=r["card_count"],
        )
        for r in rows
    ]
    return DataResponse(data=items)


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

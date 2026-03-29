"""Health check endpoint."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Return service health status, optionally pinging the database."""
    await request.app.state.db_pool.fetchval("SELECT 1")
    return {"status": "ok"}

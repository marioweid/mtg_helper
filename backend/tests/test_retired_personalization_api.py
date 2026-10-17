"""Public API contracts for removed personalization features."""

import pytest
from httpx import ASGITransport, AsyncClient

from mtg_helper.main import app

pytestmark = pytest.mark.no_db


def test_openapi_omits_retired_personalization_contracts() -> None:
    """The public schema must not advertise retired personalization APIs."""
    schema = app.openapi()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    assert not any("/coach/memory" in path for path in paths)
    assert "/api/v1/me/preferences" not in paths
    assert "/api/v1/me/ranking-weights" not in paths
    assert "/api/v1/decks/{deck_id}/feedback" not in paths
    assert not any(
        "Memory" in name or "Preference" in name or "RankingWeight" in name for name in components
    )


@pytest.mark.asyncio
async def test_retired_personalization_routes_return_not_found() -> None:
    """Removed routes must not reserve paths ahead of authentication or deck lookup."""
    deck_id = "00000000-0000-0000-0000-000000000000"
    paths = [
        ("get", f"/api/v1/decks/{deck_id}/coach/memory"),
        ("put", f"/api/v1/decks/{deck_id}/coach/memory"),
        ("post", "/api/v1/me/preferences"),
        ("get", "/api/v1/me/preferences"),
        ("delete", "/api/v1/me/preferences/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/v1/me/ranking-weights"),
        ("put", "/api/v1/me/ranking-weights"),
        ("post", f"/api/v1/decks/{deck_id}/feedback"),
        ("get", f"/api/v1/decks/{deck_id}/feedback"),
        ("delete", f"/api/v1/decks/{deck_id}/feedback/{deck_id}"),
    ]
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for method, path in paths:
            response = await client.request(method, path, json={})
            assert response.status_code == 404

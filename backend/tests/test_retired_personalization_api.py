"""Public API contracts for removed personalization features."""

from uuid import UUID

from pydantic_ai.models.test import TestModel

from mtg_helper.main import app
from mtg_helper.services import mtg_assistant
from tests.conftest import create_test_deck


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


async def test_memory_routes_are_absent_for_an_authenticated_owned_deck(client) -> None:
    """The retired memory path stays 404 after valid deck authorization can succeed."""
    deck_id = await create_test_deck(client)

    for method in ("get", "put"):
        response = await getattr(client, method)(f"/api/v1/decks/{deck_id}/coach/memory", json={})
        assert response.status_code == 404

    model = TestModel(call_tools=[], custom_output_args={"mode": "chat", "reply": "Answer"})
    with mtg_assistant.get_agent().override(model=model):
        response = await client.post(f"/api/v1/decks/{deck_id}/coach", json={"message": "Hello"})
    assert response.status_code == 200
    assistant = response.json()["data"]
    assert assistant["reply"] == "Answer"
    assert "coach_memory" not in assistant
    assert "memory_updated" not in assistant


async def test_other_retired_routes_are_absent_while_account_and_collections_remain(client) -> None:
    """Valid authenticated account routes remain available beside retired 404s."""
    deck_id = await create_test_deck(client)
    feedback_id = UUID(deck_id)
    routes = [
        ("post", "/api/v1/me/preferences", {}),
        ("get", "/api/v1/me/preferences", None),
        ("delete", f"/api/v1/me/preferences/{feedback_id}", None),
        ("get", "/api/v1/me/ranking-weights", None),
        ("put", "/api/v1/me/ranking-weights", {}),
        ("post", f"/api/v1/decks/{deck_id}/feedback", {}),
        ("get", f"/api/v1/decks/{deck_id}/feedback", None),
        ("delete", f"/api/v1/decks/{deck_id}/feedback/{feedback_id}", None),
    ]
    for method, path, body in routes:
        response = (
            await getattr(client, method)(path, json=body)
            if body is not None
            else await getattr(client, method)(path)
        )
        assert response.status_code == 404

    account = await client.get("/api/v1/me")
    assert account.status_code == 200
    updated = await client.patch("/api/v1/me", json={"display_name": "Updated Test User"})
    assert updated.status_code == 200
    created = await client.post("/api/v1/me/collections", json={"name": "Retained collection"})
    assert created.status_code == 201
    collections = await client.get("/api/v1/me/collections")
    assert collections.status_code == 200
    assert [item["name"] for item in collections.json()["data"]] == ["Retained collection"]

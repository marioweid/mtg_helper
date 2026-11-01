"""Authenticated Tutor guide lifecycle checks."""

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID

FOREST_SCRYFALL_ID = UUID("6d7b8d2c-36f5-40e7-91de-9c8c1b44da67")


async def _deck_id(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Tutor test deck"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _add_opening_hand_cards(client: AsyncClient, deck_id: str) -> None:
    """Add enough actual mainboard copies for deterministic worked hands."""
    response = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 7},
    )
    assert response.status_code == 201


async def _finished_state(client: AsyncClient, deck_id: str) -> dict[str, object]:
    """Read a generation until its durable status reaches a terminal state."""
    for _ in range(20):
        await asyncio.sleep(0)
        response = await client.get(f"/api/v1/decks/{deck_id}/tutor")
        run = response.json()["data"]["latest_run"]
        if run["status"] != "running":
            return run
    raise AssertionError("Tutor run did not reach a terminal state")


def _valid_guide() -> object:
    """Return a teacher result with three independently legal seven-card examples."""
    from mtg_helper.models.tutor import TutorGuideDraft

    return TutorGuideDraft(
        title="Hazel guide",
        content="Interpretation: build a token engine.",
        opening_hands=[
            {"decision": "keep", "cards": ["Forest"] * 7, "explanation": "Keep mana."},
            {"decision": "mulligan", "cards": ["Forest"] * 7, "explanation": "No spells."},
            {
                "decision": "context-dependent",
                "cards": ["Forest"] * 7,
                "explanation": "Depends on the table.",
            },
        ],
    )


@pytest.mark.asyncio
async def test_setup_saves_mode_without_starting_a_guide(client: AsyncClient) -> None:
    """Tutor mode is owner-saved and setup remains a no-model action."""
    deck_id = await _deck_id(client)

    saved = await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    assert saved.status_code == 200
    assert saved.json()["data"]["mode"] == "cedh"
    assert saved.json()["data"]["latest_run"] is None

    loaded = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert loaded.status_code == 200
    assert loaded.json()["data"]["mode"] == "cedh"
    assert loaded.json()["data"]["latest_run"] is None


def test_tutor_fixture_commander_is_stable() -> None:
    """The shared Tutor fixture uses the existing deterministic commander identity."""
    assert UUID(str(HAZEL_SCRYFALL_ID)).version == 4


@pytest.mark.asyncio
async def test_freshness_marks_saved_guide_historical_after_actual_card_change(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Actual list identity, rather than a deck timestamp, controls guide freshness."""
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})

    created = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert created.status_code == 200
    guide = await _finished_state(client, deck_id)
    assert guide["status"] == "succeeded"
    assert guide["current"] is True

    changed = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67"},
    )
    assert changed.status_code == 201
    historical = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert historical.json()["data"]["latest_run"]["current"] is False


@pytest.mark.asyncio
async def test_freshness_ignores_a_quantity_split_between_printings(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Printing rows with one Oracle identity remain the same Lerndeck."""
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    added = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 7},
    )
    assert added.status_code == 201
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    pool = db_pool
    async with pool.acquire() as conn:
        printing = await conn.fetchrow(
            """
            INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, oracle_text, type_line)
            SELECT gen_random_uuid(), oracle_id, name, color_identity, oracle_text, type_line
            FROM cards WHERE scryfall_id = $1 RETURNING id
            """,
            FOREST_SCRYFALL_ID,
        )
        await conn.execute(
            "UPDATE deck_cards SET quantity=6 WHERE deck_id=$1 AND card_id=("
            "SELECT id FROM cards WHERE scryfall_id=$2)",
            UUID(deck_id),
            FOREST_SCRYFALL_ID,
        )
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id, quantity) VALUES ($1, $2, 1)",
            UUID(deck_id),
            printing["id"],
        )

    state = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert state.json()["data"]["latest_run"]["current"] is True


@pytest.mark.asyncio
async def test_changed_mode_supersedes_a_blocked_generation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delayed guide cannot publish after its Tutor-Modus changes."""
    from mtg_helper.services.tutor import commander

    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_teacher(_input: object) -> object:
        started.set()
        await release.wait()
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", blocked_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    started_response = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert started_response.status_code == 200
    await started.wait()

    changed = await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    assert changed.status_code == 200
    release.set()
    run = await _finished_state(client, deck_id)
    assert run["status"] == "superseded"
    assert run["current"] is False


@pytest.mark.asyncio
async def test_runs_rejects_command_zone_cards_from_worked_opening_hands(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guide cannot publish a commander as an opening-hand card."""
    from mtg_helper.models.tutor import TutorGuideDraft
    from mtg_helper.services.tutor import commander

    async def invalid_teacher(_input: object) -> TutorGuideDraft:
        return TutorGuideDraft(
            title="Invalid guide",
            content="Interpretation: this must not publish.",
            opening_hands=[
                {
                    "decision": "keep",
                    "cards": ["Hazel of the Rootbloom"] + ["Forest"] * 6,
                    "explanation": "The commander cannot be here.",
                },
                {"decision": "mulligan", "cards": ["Forest"] * 7, "explanation": "No spells."},
                {
                    "decision": "context-dependent",
                    "cards": ["Forest"] * 7,
                    "explanation": "Depends on the table.",
                },
            ],
        )

    monkeypatch.setattr(commander, "generate", invalid_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "failed"


@pytest.mark.asyncio
async def test_evidence_marks_malformed_combo_coverage_and_retains_exact_rules(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed source data is a visible gap, never trusted as no matching line."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def malformed_combos(*_args: object) -> object:
        return {"unexpected": "not a Commander Spellbook result"}

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", malformed_combos)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    evidence = run["evidence"]
    assert run["status"] == "succeeded"
    assert evidence["sources"]["combos"] == "malformed: Commander Spellbook response"
    assert (
        "Combo coverage is unavailable; no missing line is treated as absent."
        in evidence["warnings"]
    )
    assert {rule["identifier"] for rule in evidence["rules"]} >= {
        "122.1",
        "603.10a",
        "608.2h",
        "903.3",
    }


@pytest.mark.asyncio
async def test_evidence_warns_when_pinned_rules_are_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing rules resource remains distinct from a source with zero results."""
    from mtg_helper.models.combos import ComboListResponse
    from mtg_helper.services import combo_service
    from mtg_helper.services.recommendations import source_repository
    from mtg_helper.services.tutor import commander

    async def no_combos(*_args: object) -> ComboListResponse:
        return ComboListResponse(active=[], almost_there=[])

    def missing_rules() -> tuple[bytes, str]:
        raise OSError("rules resource unavailable")

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(source_repository, "rules_resource", missing_rules)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["evidence"]["sources"]["rules"] == "unavailable: rules resource OSError"
    assert (
        "Rules coverage is unavailable; rule-dependent claims are unverified."
        in run["evidence"]["warnings"]
    )


@pytest.mark.asyncio
async def test_persistence_removes_saved_tutor_evidence_with_its_deck(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deck deletion cascades runs so late publication cannot recreate Tutor data."""
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"

    deleted = await client.delete(f"/api/v1/decks/{deck_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).status_code == 404
    count = await db_pool.fetchval(
        "SELECT count(*) FROM tutor_runs WHERE deck_id=$1", UUID(deck_id)
    )
    assert count == 0

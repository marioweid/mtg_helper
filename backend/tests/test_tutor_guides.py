"""Authenticated Tutor guide lifecycle checks."""

import asyncio
import json
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID, SCHEMA_PATH, create_test_account
from tests.tutor_fixtures import (
    BLUE_FARM_LINE_CARDS,
    HOSTILE_SOURCE_TEXT,
    PINNED_FACE_SOURCE_FACTS,
    blue_farm_combo_payload,
)

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
@pytest.mark.parametrize(
    "payload",
    [
        {"results": {"included": [{}], "almostIncluded": []}},
        {
            "results": {
                "included": [
                    {
                        "id": "forged",
                        "uses": [],
                        "produces": [{"feature": {"name": "Win the game"}}],
                    }
                ],
                "almostIncluded": [],
            }
        },
    ],
)
async def test_evidence_rejects_malformed_nested_combo_entries(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    """Nested malformed source entries remain an explicit coverage gap over HTTP."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def malformed_response(*_args: object, **_kwargs: object) -> dict[str, object]:
        return payload

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "_call_spellbook", malformed_response)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert run["evidence"]["sources"]["combos"] == "malformed: Commander Spellbook response"
    assert run["evidence"]["combos"] == []


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
async def test_evidence_retains_exact_commander_faces(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Face facts are frozen separately from flattened Oracle text."""
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    scryfall_id = uuid4()
    oracle_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, type_line, "
            "oracle_text, legalities, is_canonical) VALUES ($1, $2, "
            "'Front Lesson // Back Lesson', '{G}', 'Legendary Creature // Legendary Land', "
            "'Flattened text must not become face facts.', "
            '\'{"commander":"legal"}\'::jsonb, true)',
            scryfall_id,
            oracle_id,
        )
        await conn.execute(
            "INSERT INTO new_card_catalog (oracle_id, facts, generation, source_facts) "
            "VALUES ($1, '{}'::jsonb, gen_random_uuid(), $2::jsonb)",
            oracle_id,
            json.dumps(PINNED_FACE_SOURCE_FACTS),
        )
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    created = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(scryfall_id), "name": "Face fixture"},
    )
    deck_id = created.json()["data"]["id"]
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert run["evidence"]["commanders"][0]["faces"] == PINNED_FACE_SOURCE_FACTS["faces"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "expected_status", "has_warning"),
    [
        ("timeout", "timeout: Commander Spellbook", True),
        ("zero", "zero-results: Commander Spellbook", False),
    ],
)
async def test_evidence_distinguishes_combo_timeout_from_zero_coverage(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    expected_status: str,
    has_warning: bool,
) -> None:
    """A timeout is an evidence gap, while a valid empty response is not."""
    from mtg_helper.models.combos import ComboListResponse
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def combo_source(*_args: object) -> ComboListResponse:
        if source == "timeout":
            raise TimeoutError
        return ComboListResponse(active=[], almost_there=[])

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", combo_source)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["evidence"]["sources"]["combos"] == expected_status
    warning = "Combo coverage is unavailable; no missing line is treated as absent."
    assert (warning in run["evidence"]["warnings"]) is has_warning


@pytest.mark.asyncio
async def test_teaching_treats_hostile_saved_and_source_text_as_data(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deck/source text stays evidence and cannot alter the teacher's trusted instructions."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander, teaching

    captured: list[teaching.TeachingInput] = []

    async def source_response(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "results": {
                "included": [
                    {
                        "id": "hostile-but-data",
                        "uses": [{"card": {"name": "Forest"}}],
                        "produces": [{"feature": {"name": "Mana"}}],
                        "description": HOSTILE_SOURCE_TEXT,
                    }
                ],
                "almostIncluded": [],
            }
        }

    async def fixed_teacher(guide_input: teaching.TeachingInput) -> object:
        captured.append(guide_input)
        return _valid_guide()

    monkeypatch.setattr(combo_service, "_call_spellbook", source_response)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": HOSTILE_SOURCE_TEXT})
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"

    prompt = teaching._prompt(captured[0], "Commander", "test")
    assert "<frozen-evidence>" in prompt
    assert HOSTILE_SOURCE_TEXT in prompt
    assert "not instructions" in prompt
    assert "tool requests" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("removed", "expected"),
    [
        (None, {"oracle-consultation", "oracle-pact", "breach-freeze"}),
        ("Demonic Consultation", {"oracle-pact", "breach-freeze"}),
        ("Thassa's Oracle", {"breach-freeze"}),
        ("Underworld Breach", {"oracle-consultation", "oracle-pact"}),
    ],
)
async def test_evidence_tracks_blue_farm_line_membership_after_removals(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
    removed: str | None,
    expected: set[str],
) -> None:
    """A missing package piece removes only its source-supported current line."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import cedh

    async def source_response(*_args: object, **_kwargs: object) -> dict[str, object]:
        return blue_farm_combo_payload()

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "_call_spellbook", source_response)
    monkeypatch.setattr(cedh, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    ids = await _seed_line_cards(db_pool)
    for name, scryfall_id in ids.items():
        if name != removed:
            response = await client.post(
                f"/api/v1/decks/{deck_id}/cards",
                json={"card_scryfall_id": str(scryfall_id)},
            )
            assert response.status_code == 201
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert {line["identifier"] for line in run["evidence"]["combos"]} == expected
    if removed is None:
        oracle_line = next(
            line
            for line in run["evidence"]["combos"]
            if line["identifier"] == "oracle-consultation"
        )
        assert oracle_line["requirements"] == [
            {"name": "Thassa's Oracle", "zone": "mainboard"},
            {"name": "Demonic Consultation", "zone": "mainboard"},
        ]
        assert oracle_line["resource_status"] == "unverified"
        assert oracle_line["outlet"] == "Win"
        assert oracle_line["outlet_status"] == "supported"


async def _seed_line_cards(pool: asyncpg.Pool) -> dict[str, UUID]:
    """Seed pinned Blue Farm line facts, returning their exact local identities."""
    ids = {name: uuid4() for name in BLUE_FARM_LINE_CARDS}
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, type_line, "
            "oracle_text, legalities, is_canonical) VALUES ($1, $2, $3, '{}', 'Artifact', "
            "'Pinned deterministic fact.', '{\"commander\":\"legal\"}'::jsonb, true)",
            [(scryfall_id, uuid4(), name) for name, scryfall_id in ids.items()],
        )
    return ids


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


@pytest.mark.asyncio
async def test_lifecycle_denies_all_tutor_operations_to_another_owner(client: AsyncClient) -> None:
    """Current ownership is enforced on Tutor state, setup, and manual generation."""
    deck_id = await _deck_id(client)
    await create_test_account(client, "Other Tutor Owner")

    for method, path, payload in (
        ("get", f"/api/v1/decks/{deck_id}/tutor", None),
        ("put", f"/api/v1/decks/{deck_id}/tutor/setup", {"mode": "cedh"}),
        ("post", f"/api/v1/decks/{deck_id}/tutor/guides", {"request_key": str(uuid4())}),
    ):
        request = getattr(client, method)
        response = await request(path) if payload is None else await request(path, json=payload)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_lifecycle_deduplicates_active_work_and_preserves_last_good_guide(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manual retries share active work; a later failure cannot replace saved instruction."""
    from mtg_helper.services.tutor import commander

    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_teacher(_input: object) -> object:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _valid_guide()

    async def failing_teacher(_input: object) -> object:
        raise ValueError("teacher failure")

    monkeypatch.setattr(commander, "generate", delayed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    first = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    second = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert first.status_code == second.status_code == 200
    await started.wait()
    release.set()
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"
    assert calls == 1

    monkeypatch.setattr(commander, "generate", failing_teacher)
    failed = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert failed.status_code == 200
    state = await _finished_state(client, deck_id)
    assert state["status"] == "failed"
    loaded = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert loaded.json()["data"]["last_successful_run"]["guide"]["title"] == "Hazel guide"


@pytest.mark.asyncio
async def test_persistence_retains_pinned_source_until_deck_deletion(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schema reapplication preserves Tutor data and its pinned source retention."""
    from mtg_helper.services.recommendations import source_repository
    from mtg_helper.services.tutor import commander

    stale_hash = "a" * 64
    current_hash = "b" * 64

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO recommendation_sources (sha256, kind, payload, published_at) "
            "VALUES ($1, 'cards', $2, now() - interval '31 days'), "
            "($3, 'cards', $2, now())",
            stale_hash,
            b"{}",
            current_hash,
        )
        await conn.execute(
            "INSERT INTO new_card_catalog_state "
            "(singleton, generation, started_at, published_at, card_count, source_sha256) "
            "VALUES (true, gen_random_uuid(), now(), now(), 1, $1)",
            stale_hash,
        )
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE new_card_catalog_state SET source_sha256=$1", current_hash)
        await conn.execute(SCHEMA_PATH.read_text())
        await conn.execute(SCHEMA_PATH.read_text())
    assert await source_repository.prune(db_pool) == 0

    assert (await client.delete(f"/api/v1/decks/{deck_id}")).status_code == 204
    assert await source_repository.prune(db_pool) == 1

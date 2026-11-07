"""Authenticated Tutor frozen-reference lifecycle and evidence checks."""

import asyncio
import json
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import HAZEL_SCRYFALL_ID, SCHEMA_PATH, create_test_account, set_current_account
from tests.tutor_fixtures import (
    HOSTILE_SOURCE_TEXT,
    PinnedCardFact,
    acceptance_fixtures,
    blue_farm_combo_payload,
    fixture_pinned_facts,
)

FOREST_SCRYFALL_ID = "6d7b8d2c-36f5-40e7-91de-9c8c1b44da67"
SOL_RING_SCRYFALL_ID = "3d7b8d2c-36f5-40e7-91de-9c8c1b44da67"


async def _deck_id(client: AsyncClient, name: str = "Reference learner") -> str:
    response = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": name},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _add_card(client: AsyncClient, deck_id: str, card_id: str, quantity: int = 1) -> None:
    response = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": card_id, "quantity": quantity},
    )
    assert response.status_code == 201


async def _state(client: AsyncClient, deck_id: str) -> dict[str, object]:
    response = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert response.status_code == 200
    return response.json()["data"]


def _guide() -> object:
    from mtg_helper.models.tutor import TutorGuideDraft

    return TutorGuideDraft(
        title="Reference-aware guide",
        content="Interpretation: use only actual cards for current lines.",
        opening_hands=[
            {"decision": decision, "cards": ["Forest"] * 7, "explanation": "Actual cards."}
            for decision in ("keep", "mulligan", "context-dependent")
        ],
    )


async def _finished(client: AsyncClient, deck_id: str) -> dict[str, object]:
    for _ in range(30):
        state = await _state(client, deck_id)
        run = state["latest_run"]
        if run["status"] != "running":
            return run
        await asyncio.sleep(0)
    raise AssertionError("Tutor run did not finish")


async def _freeze_current(client: AsyncClient, deck_id: str) -> dict[str, object]:
    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    assert preview.status_code == 200
    confirmed = await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": preview.json()["data"]["preview_id"]},
    )
    assert confirmed.status_code == 200
    return confirmed.json()["data"]["reference"]


async def _seed_facts(pool: asyncpg.Pool, facts: dict[str, PinnedCardFact]) -> dict[str, UUID]:
    ids = {name: uuid4() for name in facts}
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO cards (scryfall_id, oracle_id, name, mana_cost, cmc, type_line, "
            "oracle_text, color_identity, legalities, is_canonical) VALUES "
            "($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,true)",
            [
                (
                    ids[name],
                    UUID(fact.oracle_id),
                    fact.canonical_name or name,
                    fact.mana_cost,
                    fact.cmc,
                    fact.type_line,
                    fact.oracle_text,
                    list(fact.color_identity),
                    json.dumps({"commander": fact.commander_legality}),
                )
                for name, fact in facts.items()
            ],
        )
    return ids


@pytest.mark.asyncio
async def test_context_current_reference_is_confirmed_frozen_and_removable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current-list selection freezes exact cards without editing or teaching the Lerndeck."""
    from mtg_helper.services.tutor import commander

    async def unexpected_teacher(_input: object) -> object:
        raise AssertionError("Reference operations must not call a model")

    monkeypatch.setattr(commander, "generate", unexpected_teacher)
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)

    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    assert preview.status_code == 200
    candidate = preview.json()["data"]
    assert candidate["reference"]["source"] == "current_deck"
    assert candidate["reference"]["commanders"][0]["name"] == "Hazel of the Rootbloom"
    assert candidate["reference"]["cards"] == [
        {
            "oracle_id": "6d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
            "name": "Forest",
            "quantity": 7,
            "type_line": "Basic Land — Forest",
            "oracle_text": "{T}: Add {G}.",
            "mana_cost": None,
            "cmc": 0.0,
            "color_identity": ["G"],
            "legalities": {"commander": "legal"},
            "faces": [],
        }
    ]
    assert (await _state(client, deck_id))["reference"] is None

    confirmed = await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": candidate["preview_id"]},
    )
    assert confirmed.status_code == 200
    frozen = confirmed.json()["data"]["reference"]
    assert frozen["version"] == candidate["reference"]["version"]
    assert frozen["captured_at"] == candidate["reference"]["captured_at"]

    await _add_card(client, deck_id, SOL_RING_SCRYFALL_ID)
    changed = await _state(client, deck_id)
    assert changed["reference"] == frozen
    assert changed["reference_differences"]["added"] == [
        {
            "name": "Sol Ring",
            "oracle_id": "3d7b8d2c-aaaa-40e7-91de-9c8c1b44da67",
            "reference_quantity": 0,
            "actual_quantity": 1,
        }
    ]

    removed = await client.delete(f"/api/v1/decks/{deck_id}/tutor/reference")
    assert removed.status_code == 200
    assert removed.json()["data"]["reference"] is None
    assert removed.json()["data"]["reference_differences"] is None


@pytest.mark.asyncio
async def test_context_owned_preview_cannot_replace_until_confirmed_and_survives_source_deletion(
    client: AsyncClient,
) -> None:
    """Owned-deck replacement is explicit and its frozen provenance has no source dependency."""
    deck_id = await _deck_id(client)
    source_id = await _deck_id(client, "Owned reference source")
    await _add_card(client, source_id, FOREST_SCRYFALL_ID, 7)
    await _add_card(client, source_id, SOL_RING_SCRYFALL_ID)
    current = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": current.json()["data"]["preview_id"]},
    )
    before = (await _state(client, deck_id))["reference"]

    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview",
        json={
            "source": "owned",
            "source_deck_id": source_id,
            "source_url": "https://example.invalid/reference-not-fetched",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["reference"]["source"] == "owned_deck"
    assert preview.json()["data"]["reference"]["source_deck_id"] == source_id
    assert (await _state(client, deck_id))["reference"] == before

    confirmed = await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": preview.json()["data"]["preview_id"]},
    )
    assert confirmed.status_code == 200
    frozen = confirmed.json()["data"]["reference"]
    assert frozen["version"] != before["version"]
    assert frozen["source_url"] == "https://example.invalid/reference-not-fetched"
    assert {card["name"]: card["quantity"] for card in frozen["cards"]} == {
        "Forest": 7,
        "Sol Ring": 1,
    }

    assert (await client.delete(f"/api/v1/decks/{source_id}")).status_code == 204
    assert (await _state(client, deck_id))["reference"] == frozen


@pytest.mark.asyncio
async def test_evidence_pasted_reference_rejects_unresolved_and_mismatched_without_replacement(
    client: AsyncClient,
) -> None:
    """Pasted text resolves fully before preview and never partially replaces a saved snapshot."""
    deck_id = await _deck_id(client)
    current = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": current.json()["data"]["preview_id"]},
    )
    before = (await _state(client, deck_id))["reference"]
    url = f"/api/v1/decks/{deck_id}/tutor/reference/preview"

    unresolved = await client.post(
        url,
        json={
            "source": "pasted",
            "text": "1 Hazel of the Rootbloom *CMDR*\n1 Card That Does Not Exist ZZZ",
        },
    )
    assert unresolved.status_code == 422
    assert "Unresolved" in unresolved.json()["error"]["message"]
    mismatch = await client.post(
        url,
        json={"source": "pasted", "text": "1 Rhystic Study *CMDR*\n1 Forest"},
    )
    assert mismatch.status_code == 422
    assert "commander" in mismatch.json()["error"]["message"].lower()
    empty = await client.post(url, json={"source": "pasted", "text": "\n // Lands\n"})
    assert empty.status_code == 422
    assert (await _state(client, deck_id))["reference"] == before

    valid = await client.post(
        url,
        json={
            "source": "pasted",
            "text": (
                "1 Hazel of the Rootbloom *CMDR*\n7 Forest\n1 Sol Ring\n"
                "SIDEBOARD:\n1 Doubling Season"
            ),
        },
    )
    assert valid.status_code == 200
    pasted = valid.json()["data"]["reference"]
    assert pasted["source"] == "pasted_text"
    assert {card["name"]: card["quantity"] for card in pasted["cards"]} == {
        "Forest": 7,
        "Sol Ring": 1,
    }
    assert all(card["name"] != "Doubling Season" for card in pasted["cards"])


@pytest.mark.asyncio
async def test_context_reference_version_controls_freshness_and_reaches_teacher(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reference changes make guides historical and the next manual run captures the version."""
    from mtg_helper.services.tutor import commander
    from mtg_helper.services.tutor.teaching import TeachingInput

    observed: list[TeachingInput] = []

    async def teacher(guide_input: TeachingInput) -> object:
        observed.append(guide_input)
        return _guide()

    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    baseline = await _finished(client, deck_id)
    assert baseline["current"] is True

    frozen = await _freeze_current(client, deck_id)
    historical = await _state(client, deck_id)
    assert historical["latest_run"]["current"] is False
    assert historical["latest_run"]["id"] == baseline["id"]
    assert len(observed) == 1

    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    current = await _finished(client, deck_id)
    assert current["status"] == "succeeded" and current["current"] is True
    assert observed[-1].evidence.reference is not None
    assert str(observed[-1].evidence.reference.version) == frozen["version"]
    assert current["evidence"]["reference"] == frozen
    assert current["evidence"]["reference_differences"] == {"missing": [], "added": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["replace", "remove"])
async def test_context_reference_change_supersedes_delayed_run_without_automatic_generation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """A delayed completion cannot publish against a replaced or removed reference version."""
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def delayed(_input: object) -> object:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return _guide()

    monkeypatch.setattr(commander, "generate", delayed)
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await _freeze_current(client, deck_id)
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()

    if operation == "replace":
        await _freeze_current(client, deck_id)
    else:
        assert (await client.delete(f"/api/v1/decks/{deck_id}/tutor/reference")).status_code == 200
    run = await _finished(client, deck_id)
    assert run["status"] == "superseded"
    release.set()
    await asyncio.sleep(0)
    assert (await _state(client, deck_id))["latest_run"]["guide"] is None
    assert calls == 1


@pytest.mark.asyncio
async def test_evidence_blue_farm_missing_package_retains_actual_lines_and_optional_restoration(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing Oracle and Consultation preserves Pact and Breach as actual, not reference-only."""
    from mtg_helper.models.tutor import TutorGuideDraft
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import cedh, teaching

    fixture = acceptance_fixtures()[1]
    facts = fixture_pinned_facts(fixture)
    ids = await _seed_facts(db_pool, facts)
    created = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(ids["Kraum, Ludevic's Opus"]),
            "partner_scryfall_id": str(ids["Tymna the Weaver"]),
            "name": fixture.name,
        },
    )
    assert created.status_code == 201
    deck_id = created.json()["data"]["id"]
    for quantity, name in fixture.mainboard:
        await _add_card(client, deck_id, str(ids[name]), quantity)
    frozen = await _freeze_current(client, deck_id)
    for name in ("Thassa's Oracle", "Demonic Consultation"):
        response = await client.delete(f"/api/v1/decks/{deck_id}/cards/{ids[name]}")
        assert response.status_code == 204

    async def combos(*_args: object, **_kwargs: object) -> object:
        return blue_farm_combo_payload()

    observed: list[teaching.TeachingInput] = []

    async def teacher(guide_input: teaching.TeachingInput) -> TutorGuideDraft:
        observed.append(guide_input)
        hand = [card.name for card in guide_input.evidence.cards[:7]]
        return TutorGuideDraft(
            title="Blue Farm after cuts",
            content="Interpretation: Breach remains; Oracle lines need their actual pieces.",
            opening_hands=[
                {"decision": decision, "cards": hand, "explanation": "Actual list cards."}
                for decision in ("keep", "mulligan", "context-dependent")
            ],
        )

    monkeypatch.setattr(combo_service, "_call_spellbook", combos)
    monkeypatch.setattr(cedh, "generate", teacher)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    run = await _finished(client, deck_id)

    assert run["status"] == "succeeded"
    actual_names = {card["name"] for card in run["evidence"]["cards"]}
    assert "Thassa's Oracle" not in actual_names
    assert "Demonic Consultation" not in actual_names
    assert {
        "Tainted Pact",
        "Underworld Breach",
        "Lion's Eye Diamond",
        "Brain Freeze",
    } <= actual_names
    assert sum(card["quantity"] for card in run["evidence"]["cards"]) + 2 == 98
    assert run["evidence"]["reference"] == frozen
    assert {item["name"] for item in run["evidence"]["reference_differences"]["missing"]} == {
        "Thassa's Oracle",
        "Demonic Consultation",
    }
    assert {line["identifier"] for line in run["evidence"]["combos"]} == {"breach-freeze"}
    assert {card["name"] for card in run["evidence"]["optional_suggestions"]} == {
        "Thassa's Oracle",
        "Demonic Consultation",
    }

    prompt = teaching._prompt(observed[0], "cEDH", "test")
    assert "reference-only" in prompt
    assert "optional ideas" in prompt
    assert "not actual cards" in prompt
    assert "Do not demand" in prompt


@pytest.mark.asyncio
async def test_context_printing_only_split_preserves_reference_comparison(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Reference differences use Oracle identity and quantity, not a physical printing row."""
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)
    frozen = await _freeze_current(client, deck_id)
    async with db_pool.acquire() as conn:
        printing = await conn.fetchrow(
            "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, oracle_text, "
            "type_line, legalities, is_canonical) SELECT $1, oracle_id, name, color_identity, "
            "oracle_text, type_line, legalities, false FROM cards WHERE scryfall_id=$2 "
            "RETURNING id",
            uuid4(),
            UUID(FOREST_SCRYFALL_ID),
        )
        await conn.execute(
            "UPDATE deck_cards SET quantity=6 WHERE deck_id=$1 AND card_id=("
            "SELECT id FROM cards WHERE scryfall_id=$2)",
            UUID(deck_id),
            UUID(FOREST_SCRYFALL_ID),
        )
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id, quantity) VALUES ($1,$2,1)",
            UUID(deck_id),
            printing["id"],
        )

    state = await _state(client, deck_id)
    assert state["reference"] == frozen
    assert state["reference_differences"] == {"missing": [], "added": []}


@pytest.mark.asyncio
async def test_persistence_reference_and_preview_operations_enforce_current_ownership(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Another account and anonymous callers cannot read, select, confirm, or remove references."""
    from mtg_helper.auth import get_current_account
    from mtg_helper.main import app
    from mtg_helper.models.accounts import AccountResponse

    deck_id = await _deck_id(client)
    source_id = await _deck_id(client, "Private reference source")
    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    preview_id = preview.json()["data"]["preview_id"]
    await client.put(f"/api/v1/decks/{deck_id}/tutor/reference", json={"preview_id": preview_id})
    owner = AccountResponse.model_validate(
        dict(await db_pool.fetchrow("SELECT * FROM accounts WHERE email='default@test.local'"))
    )
    await create_test_account(client, "Reference Stranger")
    other_deck = await _deck_id(client, "Stranger learner")

    for method, path, payload in (
        ("get", f"/api/v1/decks/{deck_id}/tutor", None),
        ("post", f"/api/v1/decks/{deck_id}/tutor/reference/preview", {"source": "current"}),
        (
            "post",
            f"/api/v1/decks/{deck_id}/tutor/reference/preview",
            {"source": "owned", "source_deck_id": source_id},
        ),
        ("put", f"/api/v1/decks/{deck_id}/tutor/reference", {"preview_id": preview_id}),
        ("delete", f"/api/v1/decks/{deck_id}/tutor/reference", None),
        (
            "post",
            f"/api/v1/decks/{other_deck}/tutor/reference/preview",
            {"source": "owned", "source_deck_id": source_id},
        ),
    ):
        response = await client.request(method, path, json=payload)
        assert response.status_code == 404

    app.dependency_overrides.pop(get_current_account)
    try:
        anonymous = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    finally:
        set_current_account(owner)
    assert anonymous.status_code == 401
    assert (await _state(client, deck_id))["reference"]["source_deck_id"] == deck_id


@pytest.mark.asyncio
async def test_persistence_schema_reapplication_and_source_pruning_keep_frozen_snapshot(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Schema upgrades and source maintenance cannot rewrite or invalidate frozen provenance."""
    from mtg_helper.services.recommendations import source_repository

    deck_id = await _deck_id(client)
    source_id = await _deck_id(client, "Disposable origin")
    await _add_card(client, source_id, FOREST_SCRYFALL_ID, 7)
    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview",
        json={"source": "owned", "source_deck_id": source_id, "source_url": "metadata only"},
    )
    await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": preview.json()["data"]["preview_id"]},
    )
    frozen = (await _state(client, deck_id))["reference"]
    await db_pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload, published_at) "
        "VALUES ($1,'cards',$2,now()-interval '60 days')",
        "d" * 64,
        b"disposable old source",
    )
    await db_pool.execute(SCHEMA_PATH.read_text())
    await db_pool.execute(SCHEMA_PATH.read_text())
    assert (await client.delete(f"/api/v1/decks/{source_id}")).status_code == 204
    assert await source_repository.prune(db_pool) == 1

    state = await _state(client, deck_id)
    assert state["reference"] == frozen
    assert await db_pool.fetchval("SELECT count(*) FROM decks WHERE id=$1", UUID(deck_id)) == 1
    assert await db_pool.fetchval("SELECT count(*) FROM accounts") == 1


@pytest.mark.asyncio
async def test_persistence_target_deletion_cascades_reference_and_blocks_late_publication(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deck deletion cascades Tutor data and blocks a late teacher from recreating it."""
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed(_input: object) -> object:
        entered.set()
        await release.wait()
        return _guide()

    monkeypatch.setattr(commander, "generate", delayed)
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await _freeze_current(client, deck_id)
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()
    assert (await client.delete(f"/api/v1/decks/{deck_id}")).status_code == 204
    release.set()
    await asyncio.sleep(0)

    for table in ("tutor_references", "tutor_reference_previews", "tutor_runs"):
        assert (
            await db_pool.fetchval(f"SELECT count(*) FROM {table} WHERE deck_id=$1", UUID(deck_id))
            == 0
        )
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).status_code == 404


@pytest.mark.asyncio
async def test_evidence_unavailable_reference_facts_and_hostile_metadata_remain_honest(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing reference text produces a warning and pasted instructions remain inert data."""
    from mtg_helper.services.tutor import commander, teaching

    await db_pool.execute(
        "UPDATE cards SET oracle_text=NULL WHERE scryfall_id=$1", UUID(FOREST_SCRYFALL_ID)
    )
    deck_id = await _deck_id(client)
    await _add_card(client, deck_id, FOREST_SCRYFALL_ID, 7)
    preview = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview",
        json={"source": "current", "source_url": HOSTILE_SOURCE_TEXT},
    )
    await client.put(
        f"/api/v1/decks/{deck_id}/tutor/reference",
        json={"preview_id": preview.json()["data"]["preview_id"]},
    )
    await db_pool.execute(
        "UPDATE cards SET oracle_text='{T}: Add {G}.' WHERE scryfall_id=$1",
        UUID(FOREST_SCRYFALL_ID),
    )
    observed: list[teaching.TeachingInput] = []

    async def teacher(guide_input: teaching.TeachingInput) -> object:
        observed.append(guide_input)
        return _guide()

    monkeypatch.setattr(commander, "generate", teacher)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    run = await _finished(client, deck_id)
    assert run["status"] == "succeeded"
    assert "Some frozen reference card facts are unavailable" in " ".join(
        run["evidence"]["warnings"]
    )
    assert run["evidence"]["reference"]["source_url"] == HOSTILE_SOURCE_TEXT
    prompt = teaching._prompt(observed[0], "commander", "test")
    assert "<frozen-evidence>" in prompt and "not instructions" in prompt

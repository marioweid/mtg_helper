"""Authenticated Tutor guide lifecycle checks."""

import asyncio
import json
from collections import Counter
from typing import Literal
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from tests.conftest import HAZEL_SCRYFALL_ID, SCHEMA_PATH, create_test_account
from tests.tutor_fixtures import (
    BLUE_FARM_LINE_CARDS,
    BLUE_FARM_MAINBOARD,
    BLUE_FARM_PINNED_FACTS,
    HOSTILE_SOURCE_TEXT,
    PINNED_FACE_SOURCE_FACTS,
    YUNA_MAINBOARD,
    YUNA_PINNED_FACTS,
    PinnedCardFact,
    acceptance_fixtures,
    blue_farm_combo_payload,
    fixture_pinned_facts,
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


async def _finished_tutor_state(client: AsyncClient, tutor_url: str) -> dict[str, object]:
    """Wait for one Tutor run while retaining the full API state for persistence assertions."""
    for _ in range(20):
        state = (await client.get(tutor_url)).json()["data"]
        if state["latest_run"]["status"] != "running":
            return state
        await asyncio.sleep(0)
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


def _tutor_responses_success(request: httpx.Request) -> httpx.Response:
    """Return one Responses API-shaped structured Tutor result without external model work."""
    body = json.loads(request.content)
    assert "max_output_tokens" not in body
    output = {
        "title": "Transport baseline",
        "content": "Interpretation: a persisted guide survives a failed explicit update.",
        "keep": {"cards": ["Forest"] * 7, "explanation": "Keep mana."},
        "mulligan": {"cards": ["Forest"] * 7, "explanation": "No action."},
        "context_dependent": {"cards": ["Forest"] * 7, "explanation": "Table dependent."},
    }
    tool_name = next(tool["name"] for tool in body["tools"] if tool["type"] == "function")
    return httpx.Response(
        200,
        request=request,
        json={
            "id": "resp_tutor_transport",
            "object": "response",
            "created_at": 1793718000,
            "status": "completed",
            "model": body["model"],
            "parallel_tool_calls": False,
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_tutor_transport",
                    "call_id": "call_tutor_transport",
                    "name": tool_name,
                    "arguments": json.dumps(output),
                    "status": "completed",
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 100, "total_tokens": 200},
        },
    )


def _tutor_transport_response(
    request: httpx.Request,
    failure: Literal["500", "429", "timeout"],
    failed_update: bool,
) -> httpx.Response:
    """Return the requested deterministic upstream outcome for the real SDK boundary."""
    if not failed_update:
        return _tutor_responses_success(request)
    if failure == "timeout":
        raise httpx.ReadTimeout("deterministic upstream timeout", request=request)
    return httpx.Response(int(failure), request=request, json={"error": {"message": failure}})


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


@pytest.mark.asyncio
async def test_tutor_errors_use_the_standard_error_envelope(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Tutor request failures retain their status and structured error details."""
    from mtg_helper.auth import get_current_account
    from mtg_helper.main import app
    from mtg_helper.models.accounts import AccountResponse

    deck_id = await _deck_id(client)
    missing_mode = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert missing_mode.status_code == 409
    assert missing_mode.json() == {
        "error": {
            "code": "TUTOR_REQUEST_INVALID",
            "message": "Choose a Tutor mode before generating a guide",
        }
    }

    account = await db_pool.fetchrow(
        "SELECT * FROM accounts WHERE email = $1", "default@test.local"
    )
    assert account is not None
    app.dependency_overrides[get_current_account] = lambda: AccountResponse(
        id=account["id"],
        display_name=account["display_name"],
        created_at=account["created_at"],
    )
    try:
        email_required = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    finally:
        app.dependency_overrides.pop(get_current_account, None)
    assert email_required.status_code == 403
    assert email_required.json() == {
        "error": {"code": "EMAIL_REQUIRED", "message": "Account has no email"}
    }


@pytest.mark.asyncio
async def test_tutor_validation_errors_use_the_standard_error_envelope(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Reject invalid Tutor HTTP input without persisting or exposing submitted values."""
    from mtg_helper.auth import get_current_account
    from mtg_helper.main import app

    deck_id = await _deck_id(client)
    requests = (
        ("put", f"/api/v1/decks/{deck_id}/tutor/setup", {"mode": "invalid"}),
        ("post", f"/api/v1/decks/{deck_id}/tutor/guides", {"request_key": "not-a-uuid"}),
        ("get", "/api/v1/decks/not-a-uuid/tutor", None),
        ("put", f"/api/v1/decks/{deck_id}/tutor/setup", None),
    )
    for method, path, payload in requests:
        response = await client.request(method.upper(), path, json=payload)
        assert response.status_code == 422
        body = response.json()
        assert set(body) == {"error"}
        error = body["error"]
        assert error["code"] == "TUTOR_REQUEST_INVALID"
        assert isinstance(error["message"], str) and error["message"]
        assert "invalid" not in error["message"]
        if payload:
            assert all(str(value) not in response.text for value in payload.values())

    malformed = await client.put(
        f"/api/v1/decks/{deck_id}/tutor/setup",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "TUTOR_REQUEST_INVALID"
    assert await db_pool.fetchval("SELECT count(*) FROM tutor_runs") == 0

    current_account = app.dependency_overrides.pop(get_current_account)
    try:
        unauthenticated = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    finally:
        app.dependency_overrides[get_current_account] = current_account
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "UNAUTHORIZED"


def test_tutor_fixture_commander_is_stable() -> None:
    """The shared Tutor fixture uses the existing deterministic commander identity."""
    assert UUID(str(HAZEL_SCRYFALL_ID)).version == 4


def test_acceptance_fixtures_materialize_complete_lists_and_pinned_combo_facts() -> None:
    """Portable fixture data retains both supplied decks and every pinned combo fact."""
    yuna, blue_farm = acceptance_fixtures()

    assert yuna.mainboard == YUNA_MAINBOARD
    assert blue_farm.mainboard == BLUE_FARM_MAINBOARD
    assert sum(quantity for quantity, _ in yuna.mainboard) == 99
    assert sum(quantity for quantity, _ in blue_farm.mainboard) == 98
    assert {name for _, name in blue_farm.mainboard} >= set(BLUE_FARM_LINE_CARDS)
    assert set(BLUE_FARM_PINNED_FACTS) == set(BLUE_FARM_LINE_CARDS)
    blue_counts = Counter({name: quantity for quantity, name in blue_farm.mainboard})
    hand = [
        "Ancient Tomb",
        "Underground Sea",
        "Mana Vault",
        "Chrome Mox",
        "Demonic Tutor",
        "Porom's Silence Magic",
        "Swan Song",
    ]
    assert not Counter(hand) - blue_counts
    lines = blue_farm_combo_payload()["results"]["included"]
    assert {line["id"] for line in lines if isinstance(line, dict)} == {
        "oracle-consultation",
        "oracle-tainted-pact",
        "breach-freeze",
    }


def test_acceptance_fixtures_have_portable_canonical_facts_for_every_supplied_card() -> None:
    """Each supplied card retains a real canonical fact, identity, faces, and provenance."""
    for fixture in acceptance_fixtures():
        facts = fixture_pinned_facts(fixture)
        supplied_names = set(fixture.commanders) | {name for _, name in fixture.mainboard}

        assert set(facts) == supplied_names
        assert all(fact.oracle_id and fact.canonical_name for fact in facts.values())
        assert all(fact.type_line and fact.oracle_text for fact in facts.values())
        assert all(fact.commander_legality for fact in facts.values())
        assert all(
            fact.source.get("catalog") == "isolated-compose-scryfall-catalog"
            for fact in facts.values()
        )
        assert all(isinstance(fact.source.get("generation"), str) for fact in facts.values())
    yuna, blue_farm = acceptance_fixtures()
    assert fixture_pinned_facts(yuna)["Shelinda, Yevon Acolyte"].oracle_text.startswith("Lifelink")
    assert fixture_pinned_facts(blue_farm)["Tymna the Weaver"].type_line.startswith("Legendary")
    assert fixture_pinned_facts(blue_farm)["Kraum, Ludevic's Opus"].mana_cost == "{3}{U}{R}"
    assert fixture_pinned_facts(blue_farm)["Stay with Me"].canonical_name == "Rhystic Study"
    assert fixture_pinned_facts(blue_farm)["Porom's Silence Magic"].canonical_name == "Silence"
    assert fixture_pinned_facts(blue_farm)["Chaos Emerald"].canonical_name == "Lotus Petal"


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_index", [0, 1])
async def test_complete_acceptance_fixture_facts_reach_tutor_evidence(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
    fixture_index: int,
) -> None:
    """Tutor captures all supplied quantities and canonical facts for each complete Lerndeck."""
    from mtg_helper.models.tutor import TutorGuideDraft
    from mtg_helper.services.tutor import cedh, commander
    from mtg_helper.services.tutor.teaching import TeachingInput

    fixture = acceptance_fixtures()[fixture_index]
    facts = fixture_pinned_facts(fixture)
    observed: TeachingInput | None = None

    async def fixed_teacher(guide_input: TeachingInput) -> TutorGuideDraft:
        nonlocal observed
        observed = guide_input
        hand = [facts[name].canonical_name for _, name in fixture.mainboard[:7]]
        assert all(isinstance(name, str) for name in hand)
        return TutorGuideDraft(
            title=f"{fixture.name} guide",
            content="Interpretation: use the complete supplied list.",
            opening_hands=[
                {"decision": decision, "cards": hand, "explanation": "Actual list cards."}
                for decision in ("keep", "mulligan", "context-dependent")
            ],
        )

    monkeypatch.setattr(
        commander if fixture.mode == "commander" else cedh, "generate", fixed_teacher
    )
    ids = await _seed_pinned_card_facts(db_pool, facts)
    created = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(ids[fixture.commanders[0]]),
            "partner_scryfall_id": (
                str(ids[fixture.commanders[1]]) if len(fixture.commanders) == 2 else None
            ),
            "name": fixture.name,
        },
    )
    assert created.status_code == 201
    deck_id = created.json()["data"]["id"]
    for quantity, printed_name in fixture.mainboard:
        added = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            json={"card_scryfall_id": str(ids[printed_name]), "quantity": quantity},
        )
        assert added.status_code == 201, f"{printed_name}: {added.text}"
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": fixture.mode})
    started = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert started.status_code == 200

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert observed is not None
    expected_quantities = {facts[name].oracle_id: quantity for quantity, name in fixture.mainboard}
    captured_quantities = {str(card.oracle_id): card.quantity for card in observed.evidence.cards}
    assert captured_quantities == expected_quantities
    captured_commanders = {str(card.oracle_id) for card in observed.evidence.commanders}
    assert captured_commanders == {facts[name].oracle_id for name in fixture.commanders}
    persisted_cards = {card["oracle_id"]: card for card in run["evidence"]["cards"]}
    persisted_commanders = {card["oracle_id"]: card for card in run["evidence"]["commanders"]}
    for printed_name, fact in facts.items():
        persisted = (
            persisted_commanders[fact.oracle_id]
            if printed_name in fixture.commanders
            else persisted_cards[fact.oracle_id]
        )
        expected_faces = [
            {
                "name": face["name"],
                "type_line": face.get("type_line"),
                "oracle_text": face.get("oracle_text"),
            }
            for face in fact.faces
            if isinstance(face.get("name"), str)
        ]
        assert persisted["name"] == fact.canonical_name
        assert persisted["mana_cost"] == fact.mana_cost
        assert persisted["type_line"] == fact.type_line
        assert persisted["oracle_text"] == fact.oracle_text
        assert persisted["color_identity"] == list(fact.color_identity)
        assert persisted["legalities"]["commander"] == fact.commander_legality
        assert persisted["faces"] == expected_faces


@pytest.mark.asyncio
async def test_partner_color_identity_allows_partner_colors_and_rejects_outside_colors(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
) -> None:
    """Physical additions use both saved Partner commanders without weakening color validation."""
    yuna, blue_farm = acceptance_fixtures()
    blue_facts = fixture_pinned_facts(blue_farm)
    facts = {
        name: blue_facts[name]
        for name in ("Kraum, Ludevic's Opus", "Tymna the Weaver", "Ad Nauseam")
    }
    facts["Forest"] = fixture_pinned_facts(yuna)["Forest"]
    ids = await _seed_pinned_card_facts(db_pool, facts)
    created = await client.post(
        "/api/v1/decks",
        json={
            "commander_scryfall_id": str(ids["Kraum, Ludevic's Opus"]),
            "partner_scryfall_id": str(ids["Tymna the Weaver"]),
            "name": "Partner color identity",
        },
    )
    assert created.status_code == 201
    deck_id = created.json()["data"]["id"]

    partner_color = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(ids["Ad Nauseam"])},
    )
    outside_color = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(ids["Forest"])},
    )

    assert partner_color.status_code == 201
    assert outside_color.status_code == 422
    assert outside_color.json()["detail"]["code"] == "COLOR_IDENTITY_VIOLATION"


@pytest.mark.asyncio
async def test_yuna_fixture_pinned_facts_reach_the_tutor_evidence_boundary(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Commander teaching receives real Yuna engine facts from the reusable fixture."""
    from mtg_helper.models.tutor import TutorGuideDraft
    from mtg_helper.services.tutor import commander
    from mtg_helper.services.tutor.teaching import TeachingInput

    observed: TeachingInput | None = None
    yuna, blue_farm = acceptance_fixtures()
    yuna_names = {name for _, name in yuna.mainboard}
    blue_farm_names = {name for _, name in blue_farm.mainboard}
    assert set(YUNA_PINNED_FACTS) - {"Yuna, Grand Summoner"} <= yuna_names
    assert set(BLUE_FARM_PINNED_FACTS) <= blue_farm_names

    async def fixed_teacher(guide_input: TeachingInput) -> object:
        nonlocal observed
        observed = guide_input
        hand = list(YUNA_PINNED_FACTS)[1:8]
        return TutorGuideDraft(
            title="Yuna guide",
            content="Interpretation: grow counters and attack through blockers.",
            opening_hands=[
                {"decision": decision, "cards": hand, "explanation": "Actual Yuna cards."}
                for decision in ("keep", "mulligan", "context-dependent")
            ],
        )

    monkeypatch.setattr(commander, "generate", fixed_teacher)
    ids = await _seed_pinned_card_facts(db_pool, YUNA_PINNED_FACTS)
    created = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(ids["Yuna, Grand Summoner"]), "name": yuna.name},
    )
    assert created.status_code == 201
    deck_id = created.json()["data"]["id"]
    for name, scryfall_id in ids.items():
        if name == "Yuna, Grand Summoner":
            continue
        added = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            json={"card_scryfall_id": str(scryfall_id)},
        )
        assert added.status_code == 201
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": yuna.mode})
    started = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert started.status_code == 200

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert observed is not None
    assert observed.evidence.commanders[0].oracle_id == UUID(
        YUNA_PINNED_FACTS["Yuna, Grand Summoner"].oracle_id
    )
    teaching_facts = {fact.name: fact for fact in observed.evidence.cards}
    assert teaching_facts["Simic Ascendancy"].oracle_text.endswith("you win the game.")
    assert teaching_facts["Twenty-Toed Toad"].color_identity == ["U"]
    evidence = run["evidence"]
    assert (
        evidence["commanders"][0]["oracle_id"]
        == YUNA_PINNED_FACTS["Yuna, Grand Summoner"].oracle_id
    )
    facts = {card["name"]: card for card in evidence["cards"]}
    assert facts["Hardened Scales"]["oracle_text"] == (
        "If one or more +1/+1 counters would be put on a creature you control, that many plus "
        "one +1/+1 counters are put on it instead."
    )
    assert facts["Simic Ascendancy"]["mana_cost"] == "{G}{U}"
    assert facts["Twenty-Toed Toad"]["legalities"]["commander"] == "legal"


def test_teaching_candidates_mix_actual_lands_and_castable_actions() -> None:
    """Candidate construction offers useful actual-list contrast rather than all-land hands."""
    from mtg_helper.models.tutor import TutorCardFact, TutorEvidence
    from mtg_helper.services.tutor.teaching import _opening_hand_candidates

    evidence = TutorEvidence(
        commanders=[],
        cards=[
            TutorCardFact(
                oracle_id=None,
                name="Forest",
                quantity=4,
                type_line="Basic Land",
                oracle_text="",
                mana_cost=None,
                cmc=0,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Island",
                quantity=3,
                type_line="Basic Land",
                oracle_text="",
                mana_cost=None,
                cmc=0,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Sol Ring",
                quantity=1,
                type_line="Artifact",
                oracle_text="",
                mana_cost="{1}",
                cmc=1,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Swan Song",
                quantity=1,
                type_line="Instant",
                oracle_text="",
                mana_cost="{U}",
                cmc=1,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Mystic Remora",
                quantity=1,
                type_line="Enchantment",
                oracle_text="",
                mana_cost="{U}",
                cmc=1,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Rhystic Study",
                quantity=1,
                type_line="Enchantment",
                oracle_text="",
                mana_cost="{2}{U}",
                cmc=3,
            ),
            TutorCardFact(
                oracle_id=None,
                name="Doubling Season",
                quantity=1,
                type_line="Enchantment",
                oracle_text="",
                mana_cost="{4}{G}",
                cmc=6,
            ),
            TutorCardFact(
                oracle_id=None,
                name="An Offer You Can't Refuse",
                quantity=1,
                type_line="Instant",
                oracle_text="",
                mana_cost="{U}",
                cmc=1,
            ),
        ],
    )

    candidates = _opening_hand_candidates(evidence)
    assert len(candidates) >= 3
    assert all(len(hand) == 7 for hand in candidates)
    assert all(any(card not in {"Forest", "Island"} for card in hand) for hand in candidates)
    assert len({tuple(hand) for hand in candidates}) >= 3
    assert [sum(card in {"Forest", "Island"} for card in hand) for hand in candidates] == [
        3,
        1,
        2,
        3,
    ]
    assert sum(card not in {"Forest", "Island"} for card in candidates[0]) == 4


def test_teaching_candidates_bound_quantity_work_without_mutating_frozen_evidence() -> None:
    """A huge saved quantity cannot allocate more than one opening hand can use."""
    from mtg_helper.models.tutor import TutorCardFact, TutorEvidence
    from mtg_helper.services.tutor.teaching import _card_names, _opening_hand_candidates

    evidence = TutorEvidence(
        commanders=[],
        cards=[
            TutorCardFact(
                oracle_id=None,
                name="Forest",
                quantity=100_000,
                type_line="Basic Land",
                oracle_text="{T}: Add {G}.",
            ),
            TutorCardFact(
                oracle_id=None,
                name="Sol Ring",
                quantity=1,
                type_line="Artifact",
                oracle_text="{T}: Add {C}{C}.",
                mana_cost="{1}",
                cmc=1,
            ),
        ],
    )

    names = _card_names(evidence, lambda _card: True)
    candidates = _opening_hand_candidates(evidence)

    assert evidence.cards[0].quantity == 100_000
    assert names.count("Forest") == 7
    assert len(names) == 8
    assert all(len(candidate) == 7 for candidate in candidates)
    assert all(candidate.count("Forest") <= 7 for candidate in candidates)


def test_teaching_structured_output_requires_each_opening_hand_decision() -> None:
    """Named model fields make all persisted worked-hand decisions deterministic."""
    from mtg_helper.models.tutor import TutorGuideStructuredOutput

    hand = {"cards": ["Forest"] * 7, "explanation": "A tested opening-hand example."}
    draft = TutorGuideStructuredOutput(
        title="Structured guide",
        content="Interpretation: use the saved list.",
        keep=hand,
        mulligan=hand,
        context_dependent=hand,
    ).to_draft()

    assert [example.decision for example in draft.opening_hands] == [
        "keep",
        "mulligan",
        "context-dependent",
    ]
    with pytest.raises(ValidationError):
        TutorGuideStructuredOutput(
            title="Incomplete guide",
            content="Interpretation: this output must fail honestly.",
            keep=hand,
            mulligan=hand,
        )


def test_teaching_output_preserves_unbounded_guide_and_hand_prose() -> None:
    """Generated and persisted guide prose retain useful provider-sized output intact."""
    from mtg_helper.models.tutor import TutorGuideDraft, TutorGuideStructuredOutput

    title = "Detailed guide title " * 20
    content = "Guide detail. " * 5_000
    explanation = "Explain the actual hand. " * 100
    hand = {"cards": ["Forest"] * 7, "explanation": explanation}
    generated = TutorGuideStructuredOutput(
        title=title,
        content=content,
        keep=hand,
        mulligan=hand,
        context_dependent=hand,
    )
    persisted = TutorGuideDraft(
        title=title,
        content=content,
        opening_hands=generated.to_draft().opening_hands,
    )

    assert len(content) > 64_000
    assert len(explanation) > 1_200
    assert persisted.title == title
    assert persisted.content == content
    assert [hand.explanation for hand in persisted.opening_hands] == [explanation] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["500", "429", "timeout"])
async def test_runs_send_one_sdk_request_for_each_failed_manual_tutor_update(
    client: AsyncClient,
    db_pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
    failure: Literal["500", "429", "timeout"],
) -> None:
    """Real Tutor HTTP/SQL work keeps one upstream attempt and the previous guide on failure."""
    from mtg_helper.services.tutor import teaching

    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    tutor_url = f"/api/v1/decks/{deck_id}/tutor"
    assert (await client.put(tutor_url + "/setup", json={"mode": "commander"})).status_code == 200
    metadata_agent = teaching._agent("transport metadata")
    provider_host = metadata_agent.model.client.base_url.host
    assert metadata_agent.model.client.max_retries == 0
    await metadata_agent.model.client.close()
    attempts: list[str | None] = []
    fail_update = False

    async def boundary(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers.get("x-stainless-retry-count"))
        return _tutor_transport_response(request, failure, fail_update)

    original_send = httpx.AsyncClient.send
    async with httpx.AsyncClient(transport=httpx.MockTransport(boundary)) as external:

        async def external_only(
            self: httpx.AsyncClient, request: httpx.Request, **kwargs: object
        ) -> object:
            if request.url.host == provider_host:
                return await original_send(external, request, **kwargs)
            return await original_send(self, request, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "send", external_only)
        assert (
            await client.post(tutor_url + "/guides", json={"request_key": str(uuid4())})
        ).status_code == 200
        baseline = await _finished_tutor_state(client, tutor_url)
        assert baseline["latest_run"]["status"] == "succeeded"
        last_good = baseline["last_successful_run"]
        assert attempts == ["0"]
        fail_update = True
        request_key = str(uuid4())
        assert (
            await client.post(tutor_url + "/guides", json={"request_key": request_key})
        ).status_code == 200
        state = await _finished_tutor_state(client, tutor_url)

    failed_run = state["latest_run"]
    stored = await db_pool.fetchrow(
        "SELECT status, guide, finished_at FROM tutor_runs WHERE id=$1", UUID(failed_run["id"])
    )
    assert attempts == ["0", "0"]
    assert failed_run["status"] == stored["status"] == "failed"
    assert stored["guide"] is None and stored["finished_at"] is not None
    assert state["last_successful_run"] == last_good
    before_reads = len(attempts)
    for _ in range(3):
        assert (await client.get(tutor_url)).json()["data"] == state
    assert (await client.post(tutor_url + "/guides", json={"request_key": request_key})).json()[
        "data"
    ] == state
    assert len(attempts) == before_reads
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_runs WHERE deck_id=$1", UUID(deck_id))
        == 2
    )


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
async def test_freshness_uses_saved_teaching_inputs_but_not_unrelated_metadata(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Title edits are inert while a saved description changes guide teaching context."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    assert (await _finished_state(client, deck_id))["current"] is True

    title = await client.patch(f"/api/v1/decks/{deck_id}", json={"name": "Renamed deck"})
    assert title.status_code == 200
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).json()["data"]["latest_run"][
        "current"
    ] is True

    description = await client.patch(
        f"/api/v1/decks/{deck_id}", json={"description": "A different saved teaching focus."}
    )
    assert description.status_code == 200
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).json()["data"]["latest_run"][
        "current"
    ] is False


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
    "body",
    [
        b"{not-json",
        (
            b'{"results":{"included":[{"id":"overflow","uses":[{"card":{"name":"Forest"}}],'
            b'"produces":[],"popularity":1e999}],"almostIncluded":[]}}'
        ),
    ],
    ids=("invalid-json", "non-finite-popularity"),
)
async def test_evidence_classifies_malformed_http_combo_responses(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    """HTTP 200 malformed bodies remain source gaps instead of failed guide intent."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    call_spellbook = combo_service._call_spellbook

    async def malformed_http(_body: dict[str, object], *, client: object = None) -> object:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
        async with httpx.AsyncClient(transport=transport) as http_client:
            return await call_spellbook({}, client=http_client)

    monkeypatch.setattr(combo_service, "_call_spellbook", malformed_http)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "succeeded"
    assert run["evidence"]["sources"]["combos"] == "malformed: Commander Spellbook response"


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
async def test_evidence_marks_corrupt_pinned_rules_as_malformed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt rules snapshot is not reported as a merely unavailable resource."""
    from mtg_helper.models.combos import ComboListResponse
    from mtg_helper.services import combo_service
    from mtg_helper.services.recommendations import source_repository
    from mtg_helper.services.tutor import commander

    async def no_combos(*_args: object) -> ComboListResponse:
        return ComboListResponse(active=[], almost_there=[])

    def corrupt_rules() -> tuple[bytes, str]:
        return b"not a gzip stream", "a" * 64

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(source_repository, "rules_resource", corrupt_rules)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["evidence"]["sources"]["rules"] == "malformed: rules resource BadGzipFile"


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
            "'Barkchannel Pathway // Tidechannel Pathway', '{G,U}', 'Land // Land', "
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
    assert "opening_hand_candidates" in prompt
    assert "Only listed commanders begin in the command zone" in prompt
    assert "additional cost from that hand" in prompt


@pytest.mark.asyncio
async def test_runs_rejects_an_oversized_hostile_description_before_model_work(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A maliciously large saved description fails durably without a hidden paid retry."""
    from mtg_helper.services.tutor import commander, teaching

    prompt_calls = 0

    async def bounded_teacher(guide_input: teaching.TeachingInput) -> object:
        nonlocal prompt_calls
        prompt_calls += 1
        teaching._prompt(guide_input, "Commander", "test")
        return _valid_guide()

    monkeypatch.setattr(commander, "generate", bounded_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    oversized = HOSTILE_SOURCE_TEXT + "x" * (1024 * 1024)
    updated = await client.patch(f"/api/v1/decks/{deck_id}", json={"description": oversized})
    assert updated.status_code == 200
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})

    run = await _finished_state(client, deck_id)
    assert run["status"] == "failed"
    assert run["error"] == "Guide generation failed; retry explicitly."
    assert prompt_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("removed", "expected"),
    [
        (None, {"oracle-consultation", "oracle-tainted-pact", "breach-freeze"}),
        ("Demonic Consultation", {"oracle-tainted-pact", "breach-freeze"}),
        ("Thassa's Oracle", {"breach-freeze"}),
        ("Underworld Breach", {"oracle-consultation", "oracle-tainted-pact"}),
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
            "oracle_text, legalities, is_canonical) VALUES ($1, $2, $3, '{}', $4, $5, "
            '\'{"commander":"legal"}\'::jsonb, true)',
            [
                (scryfall_id, uuid4(), name, *BLUE_FARM_PINNED_FACTS[name])
                for name, scryfall_id in ids.items()
            ],
        )
    return ids


async def _seed_pinned_card_facts(
    pool: asyncpg.Pool, facts: dict[str, PinnedCardFact]
) -> dict[str, UUID]:
    """Seed real pinned fixture facts through the same card capture path used by Tutor."""
    ids = {name: uuid4() for name in facts}
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO cards (scryfall_id, oracle_id, name, mana_cost, cmc, type_line, "
            "oracle_text, color_identity, legalities, is_canonical) VALUES "
            "($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, true)",
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
        await conn.executemany(
            "INSERT INTO new_card_catalog (oracle_id, facts, generation, source_facts) "
            "VALUES ($1, '{}'::jsonb, gen_random_uuid(), $2::jsonb)",
            [
                (
                    UUID(fact.oracle_id),
                    json.dumps({"faces": list(fact.faces), "fixture_source": fact.source}),
                )
                for fact in facts.values()
            ],
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
async def test_runs_deduplicates_active_work_and_preserves_last_good_guide(
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
    request_key = uuid4()
    first = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(request_key)}
    )
    second = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(request_key)}
    )
    third = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert first.status_code == second.status_code == third.status_code == 200
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
async def test_runs_allow_only_one_active_teacher_after_a_deck_transfer(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transferred Lerndeck cannot start a second teacher before its old run finishes."""
    from mtg_helper.models.accounts import AccountResponse
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander
    from tests.conftest import set_current_account

    calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def teacher(_input: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    old_row = await db_pool.fetchrow("SELECT * FROM accounts WHERE email='default@test.local'")
    old_owner = AccountResponse.model_validate(dict(old_row))
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()

    new_account_id = await create_test_account(client, "Transferred Active Owner")
    new_email = await db_pool.fetchval(
        "SELECT email FROM accounts WHERE id=$1", UUID(new_account_id)
    )
    await db_pool.execute("UPDATE decks SET owner_email=$2 WHERE id=$1", UUID(deck_id), new_email)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    second = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert second.status_code == 200
    await asyncio.sleep(0)
    assert calls == 1
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_runs WHERE deck_id=$1 AND status='running'", UUID(deck_id)
        )
        == 1
    )

    release.set()
    for _ in range(20):
        if (
            await db_pool.fetchval(
                "SELECT count(*) FROM tutor_runs WHERE deck_id=$1 AND status='running'",
                UUID(deck_id),
            )
            == 0
        ):
            break
        await asyncio.sleep(0)
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_runs WHERE deck_id=$1 AND status='running'", UUID(deck_id)
        )
        == 0
    )
    replacement = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert replacement.status_code == 200
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"
    assert calls == 2

    set_current_account(old_owner)
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).status_code == 404


@pytest.mark.asyncio
async def test_persistence_replaces_old_active_run_index_idempotently(
    client: AsyncClient, db_pool: asyncpg.Pool
) -> None:
    """Schema reapplication upgrades an old per-owner guard without duplicate active work."""
    deck_id = UUID(await _deck_id(client))
    second_account = await db_pool.fetchval(
        "INSERT INTO accounts (display_name, email) VALUES ('Index Owner', 'index@test.local') "
        "RETURNING id"
    )
    async with db_pool.acquire() as conn:
        await conn.execute("DROP INDEX tutor_one_active_run")
        await conn.execute(
            "CREATE UNIQUE INDEX tutor_one_active_run ON tutor_runs (deck_id, account_id) "
            "WHERE status = 'running'"
        )
        await conn.executemany(
            "INSERT INTO tutor_runs (id, deck_id, account_id, request_key, mode, composition_hash, "
            "teaching_hash, manifest, evidence, token) VALUES ($1,$2,$3,$4,'commander','old','old',"
            "'{}'::jsonb,'{}'::jsonb,$5)",
            [(uuid4(), deck_id, account, uuid4(), uuid4()) for account in (second_account,)],
        )
        owner = await conn.fetchval("SELECT id FROM accounts WHERE email='default@test.local'")
        await conn.execute(
            "INSERT INTO tutor_runs (id, deck_id, account_id, request_key, mode, composition_hash, "
            "teaching_hash, manifest, evidence, token) VALUES ($1,$2,$3,$4,'commander','new','new',"
            "'{}'::jsonb,'{}'::jsonb,$5)",
            uuid4(),
            deck_id,
            owner,
            uuid4(),
            uuid4(),
        )
        await conn.execute(SCHEMA_PATH.read_text())
        await conn.execute(SCHEMA_PATH.read_text())

    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_runs WHERE deck_id=$1 AND status='running'", deck_id
        )
        == 1
    )
    index_definition = await db_pool.fetchval(
        "SELECT indexdef FROM pg_indexes WHERE indexname='tutor_one_active_run'"
    )
    assert "UNIQUE INDEX tutor_one_active_run" in index_definition
    assert "(deck_id) WHERE" in index_definition


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "not an object",
        {"results": []},
        {"results": {"included": None, "almostIncluded": []}},
        {"results": {"included": [None], "almostIncluded": []}},
        {
            "results": {
                "included": [
                    {
                        "id": "line",
                        "uses": [{"card": {"name": " "}}],
                        "produces": [{"feature": {"name": "Win"}}],
                    }
                ],
                "almostIncluded": [],
            }
        },
        {"results": {"included": [{"id": "line", "uses": "Forest"}], "almostIncluded": []}},
        {
            "results": {
                "included": [{"id": "line", "uses": [{"card": None}]}],
                "almostIncluded": [],
            }
        },
        {
            "results": {
                "included": [
                    {
                        "id": "line",
                        "uses": [{"card": {"name": "Forest"}}],
                        "produces": [{"feature": {"name": 123}}],
                    }
                ],
                "almostIncluded": [],
            }
        },
        {
            "results": {
                "included": [
                    {
                        "id": "line",
                        "uses": [{"card": {"name": "Forest"}}],
                        "produces": [],
                        "description": {"invalid": True},
                    }
                ],
                "almostIncluded": [],
            }
        },
        {
            "results": {
                "included": [
                    {
                        "id": "line",
                        "uses": [{"card": {"name": "Forest"}}],
                        "produces": [],
                        "bracketTag": {"invalid": True},
                    }
                ],
                "almostIncluded": [],
            }
        },
        {
            "results": {
                "included": [
                    {
                        "id": "line",
                        "uses": [
                            {"card": {"name": "Forest", "imageUriFrontNormal": {"invalid": True}}}
                        ],
                        "produces": [],
                    }
                ],
                "almostIncluded": [],
            }
        },
    ],
    ids=(
        "root-list",
        "root-null",
        "root-string",
        "results-list",
        "included-null",
        "null-entry",
        "blank-name",
        "uses-string",
        "null-card",
        "invalid-produce",
        "description-object",
        "bracket-object",
        "image-object",
    ),
)
async def test_evidence_persists_intent_for_malformed_combo_payload_matrix(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    """Malformed remote roots become a saved source gap after manual intent is durable."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def malformed_response(*_args: object, **_kwargs: object) -> object:
        return payload

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "_call_spellbook", malformed_response)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})

    created = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert created.status_code == 200
    run = await _finished_state(client, deck_id)
    assert run["evidence"]["sources"]["combos"] == "malformed: Commander Spellbook response"
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_runs WHERE deck_id=$1", UUID(deck_id))
        == 1
    )


@pytest.mark.asyncio
async def test_runs_publish_superseded_after_real_quantity_change(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A physical quantity writer commits before publication and supersedes that run."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def teacher(_input: object) -> object:
        entered.set()
        await release.wait()
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    created = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    run_id = UUID(created.json()["data"]["latest_run"]["id"])
    await entered.wait()
    async with db_pool.acquire() as blocker:
        transaction = blocker.transaction()
        await transaction.start()
        await blocker.fetchrow("SELECT id FROM tutor_runs WHERE id=$1 FOR UPDATE", run_id)
        release.set()
        changed = await client.patch(
            f"/api/v1/decks/{deck_id}/cards/{FOREST_SCRYFALL_ID}/quantity", json={"quantity": 8}
        )
        assert changed.status_code == 204
        await transaction.commit()
    assert (await _finished_state(client, deck_id))["status"] == "superseded"


@pytest.mark.asyncio
async def test_runs_get_is_read_only_for_an_expired_generation(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reloading observes an expired lease; startup owns interruption recovery."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def teacher(_input: object) -> object:
        entered.set()
        await release.wait()
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()
    await db_pool.execute(
        "UPDATE tutor_runs SET lease_until=now()-interval '1 second' WHERE deck_id=$1",
        UUID(deck_id),
    )
    before = await db_pool.fetchval("SELECT status FROM tutor_runs WHERE deck_id=$1", UUID(deck_id))
    response = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    after = await db_pool.fetchval("SELECT status FROM tutor_runs WHERE deck_id=$1", UUID(deck_id))
    release.set()
    assert response.status_code == 200
    assert before == after == "running"


@pytest.mark.asyncio
async def test_runs_lifecycle_recovery_interrupts_without_a_hidden_retry(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup recovery leaves an explicit retryable interruption, never a second teacher call."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander
    from mtg_helper.services.tutor.repository import interrupt_running

    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def teacher(_input: object) -> object:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()
    await interrupt_running(db_pool)
    release.set()

    state = (await client.get(f"/api/v1/decks/{deck_id}/tutor")).json()["data"]["latest_run"]
    assert state["status"] == "interrupted"
    assert state["error"] == "Guide generation was interrupted; retry explicitly."
    assert calls == 1


@pytest.mark.asyncio
async def test_persistence_transferred_owner_can_save_a_tutor_mode(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A setup belongs to the current deck owner after an authorized transfer."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import cedh

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(cedh, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    account_id = await create_test_account(client, "Transferred Tutor Owner")
    email = await db_pool.fetchval("SELECT email FROM accounts WHERE id=$1", UUID(account_id))
    await db_pool.execute("UPDATE decks SET owner_email=$2 WHERE id=$1", UUID(deck_id), email)

    saved = await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "cedh"})
    assert saved.status_code == 200
    assert saved.json()["data"]["mode"] == "cedh"
    assert await db_pool.fetchval(
        "SELECT account_id FROM tutor_setups WHERE deck_id=$1", UUID(deck_id)
    ) == UUID(account_id)
    await _add_opening_hand_cards(client, deck_id)
    generated = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert generated.status_code == 200
    assert (await _finished_state(client, deck_id))["status"] == "succeeded"


@pytest.mark.asyncio
async def test_persistence_deletion_blocks_late_guide_publication(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delayed result cannot recreate Tutor data after its deck is deleted."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def teacher(_input: object) -> object:
        entered.set()
        await release.wait()
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    await entered.wait()
    assert (await client.delete(f"/api/v1/decks/{deck_id}")).status_code == 204
    release.set()

    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor")).status_code == 404
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_runs WHERE deck_id=$1", UUID(deck_id))
        == 0
    )


@pytest.mark.asyncio
async def test_freshness_captures_known_banned_and_off_color_warnings(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guide evidence reports already-known facts without implementing full legality."""
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander

    async def no_combos(*_args: object) -> object:
        from mtg_helper.models.combos import ComboListResponse

        return ComboListResponse(active=[], almost_there=[])

    async def fixed_teacher(_input: object) -> object:
        return _valid_guide()

    monkeypatch.setattr(combo_service, "fetch_combos", no_combos)
    monkeypatch.setattr(commander, "generate", fixed_teacher)
    deck_id = await _deck_id(client)
    await _add_opening_hand_cards(client, deck_id)
    async with db_pool.acquire() as conn:
        card = await conn.fetchrow(
            "INSERT INTO cards (scryfall_id, oracle_id, name, color_identity, type_line, "
            "oracle_text, legalities, is_canonical) VALUES ($1, $2, 'Known Problem Card', "
            "'{U}', 'Creature', '', '{\"commander\":\"banned\"}'::jsonb, true) RETURNING id",
            uuid4(),
            uuid4(),
        )
        await conn.execute(
            "INSERT INTO deck_cards (deck_id, card_id, quantity) VALUES ($1, $2, 1)",
            UUID(deck_id),
            card["id"],
        )
    await client.put(f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"})
    await client.post(f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())})
    warnings = (await _finished_state(client, deck_id))["evidence"]["warnings"]
    assert any("Commander-banned" in warning for warning in warnings)
    assert any("outside the saved commander color identity" in warning for warning in warnings)


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

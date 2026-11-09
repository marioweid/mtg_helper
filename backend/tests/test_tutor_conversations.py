"""Authenticated Tutor conversation, chapter, and history checks."""

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import (
    DOUBLING_SEASON_SCRYFALL_ID,
    HAZEL_SCRYFALL_ID,
    SCHEMA_PATH,
    create_test_account,
)
from tests.tutor_fixtures import FOREST_SCRYFALL_ID, valid_guide


async def _deck_id(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/decks",
        json={"commander_scryfall_id": str(HAZEL_SCRYFALL_ID), "name": "Conversation deck"},
    )
    assert response.status_code == 201
    deck_id = response.json()["data"]["id"]
    added = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 7},
    )
    assert added.status_code == 201
    configured = await client.put(
        f"/api/v1/decks/{deck_id}/tutor/setup", json={"mode": "commander"}
    )
    assert configured.status_code == 200
    return deck_id


async def _conversation(client: AsyncClient, deck_id: str) -> dict[str, object]:
    response = await client.get(f"/api/v1/decks/{deck_id}/tutor/conversation")
    assert response.status_code == 200
    return response.json()["data"]


async def _finished_conversation(client: AsyncClient, deck_id: str) -> dict[str, object]:
    for _ in range(30):
        state = await _conversation(client, deck_id)
        turns = state["chapters"][-1]["turns"] if state["chapters"] else []
        if turns and turns[-1]["status"] != "running":
            return state
        await asyncio.sleep(0)
    raise AssertionError("Tutor answer did not reach a terminal state")


async def _finished_guide(client: AsyncClient, deck_id: str) -> dict[str, object]:
    for _ in range(30):
        response = await client.get(f"/api/v1/decks/{deck_id}/tutor")
        guide = response.json()["data"]["latest_run"]
        if guide["status"] != "running":
            return guide
        await asyncio.sleep(0)
    raise AssertionError("Tutor guide did not reach a terminal state")


@pytest.mark.asyncio
async def test_persistence_saves_full_current_list_question_and_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A selected actual card and follow-up survive reload in one current chapter."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander

    observed = []

    async def answer(question_input: object) -> TutorAnswerDraft:
        observed.append(question_input)
        return TutorAnswerDraft(content="Develop Forest mana before committing to the engine.")

    monkeypatch.setattr(commander, "answer", answer)
    deck_id = await _deck_id(client)
    asked = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={
            "request_key": str(uuid4()),
            "question": "Explain its purpose and limitations in my deck",
            "card_name": "Forest",
        },
    )
    assert asked.status_code == 200

    state = await _finished_conversation(client, deck_id)
    assert len(state["chapters"]) == 1
    chapter = state["chapters"][0]
    assert chapter["current"] is True
    assert chapter["turns"] == [
        {
            "id": chapter["turns"][0]["id"],
            "question": "Explain its purpose and limitations in my deck",
            "answer": "Develop Forest mana before committing to the engine.",
            "card_name": "Forest",
            "status": "succeeded",
            "error": None,
            "created_at": chapter["turns"][0]["created_at"],
            "finished_at": chapter["turns"][0]["finished_at"],
        }
    ]
    assert observed[0].selected_card.name == "Forest"
    assert observed[0].selected_card_present is True
    assert (await _conversation(client, deck_id)) == state


@pytest.mark.asyncio
async def test_handoff_archives_frozen_chapter_lazily_after_coalesced_edits(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the next question compacts prior learning into one new chronological chapter."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compactions = []

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Current-list answer.")

    async def compact(compaction_input: object) -> TutorHandoffDraft:
        compactions.append(compaction_input)
        return TutorHandoffDraft(
            content="Goal: learn the engine; prior card claims need rechecking."
        )

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    deck_id = await _deck_id(client)
    first = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "What is my plan?"},
    )
    assert first.status_code == 200
    await _finished_conversation(client, deck_id)
    assert compactions == []

    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 1},
    )
    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": "Counter engine"})
    assert (await _conversation(client, deck_id))["chapters"][0]["current"] is False
    assert len((await _conversation(client, deck_id))["chapters"]) == 1

    resumed = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "What should I prioritize now?"},
    )
    assert resumed.status_code == 200
    state = await _finished_conversation(client, deck_id)
    assert len(compactions) == 1
    assert compactions[0].turns[0].question == "What is my plan?"
    assert len(state["chapters"]) == 2
    archived, current = state["chapters"]
    assert archived["current"] is False
    assert archived["turns"][0]["answer"] == "Current-list answer."
    assert current["current"] is True
    assert current["handoff_status"] == "ready"
    assert current["handoff"] == "Goal: learn the engine; prior card claims need rechecking."
    assert current["turns"][0]["question"] == "What should I prioritize now?"


@pytest.mark.asyncio
async def test_handoff_bounds_same_chapter_growth_without_truncating_saved_turns(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older turns compact lazily while model context and handoff remain bounded."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compactions = []
    recent_sizes = []

    async def answer(question_input: object) -> TutorAnswerDraft:
        recent_sizes.append(len(question_input.recent_turns))
        return TutorAnswerDraft(content="Saved answer")

    async def compact(compaction_input: object) -> TutorHandoffDraft:
        compactions.append(compaction_input)
        return TutorHandoffDraft(content="Compacted learning goals")

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    deck_id = await _deck_id(client)
    for index in range(13):
        await client.post(
            f"/api/v1/decks/{deck_id}/tutor/questions",
            json={"request_key": str(uuid4()), "question": f"Question {index}"},
        )
        await _finished_conversation(client, deck_id)

    state = await _conversation(client, deck_id)
    assert len(state["chapters"]) == 1
    chapter = state["chapters"][0]
    assert len(chapter["turns"]) == 13
    assert chapter["handoff"] == "Compacted learning goals"
    assert len(compactions) == 1
    assert len(compactions[0].turns) == 4
    assert [turn.question for turn in compactions[0].turns] == [
        "Question 0",
        "Question 1",
        "Question 2",
        "Question 3",
    ]
    assert max(recent_sizes) <= 8


@pytest.mark.asyncio
async def test_handoff_also_runs_on_explicit_guide_action_without_adding_a_turn(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manual guide action resumes learning history without fabricating a user message."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compactions = []

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Original answer")

    async def compact(_input: object) -> TutorHandoffDraft:
        compactions.append(True)
        return TutorHandoffDraft(content="Learning carried into guide context")

    async def generate(_input: object) -> object:
        return valid_guide()

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    monkeypatch.setattr(commander, "generate", generate)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Original question"},
    )
    await _finished_conversation(client, deck_id)
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(DOUBLING_SEASON_SCRYFALL_ID), "quantity": 1},
    )

    started = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert started.status_code == 200
    for _ in range(30):
        guide = (await client.get(f"/api/v1/decks/{deck_id}/tutor")).json()["data"]["latest_run"]
        if guide["status"] != "running":
            break
        await asyncio.sleep(0)
    assert guide["status"] == "succeeded"
    state = await _conversation(client, deck_id)
    assert len(compactions) == 1
    assert len(state["chapters"]) == 2
    assert state["chapters"][1]["turns"] == []
    assert state["chapters"][1]["handoff"] == "Learning carried into guide context"


@pytest.mark.asyncio
async def test_concurrency_deduplicates_requests_and_never_rebinds_delayed_answers(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duplicate keys share work and an edit makes a delayed answer explicitly superseded."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander

    calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed(_input: object) -> TutorAnswerDraft:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return TutorAnswerDraft(content="Answer for the old list only.")

    monkeypatch.setattr(commander, "answer", delayed)
    deck_id = await _deck_id(client)
    request_key = str(uuid4())
    payload = {"request_key": request_key, "question": "Explain the old list"}
    first = await client.post(f"/api/v1/decks/{deck_id}/tutor/questions", json=payload)
    duplicate = await client.post(f"/api/v1/decks/{deck_id}/tutor/questions", json=payload)
    assert first.status_code == duplicate.status_code == 200
    await entered.wait()
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 1},
    )
    release.set()
    state = await _finished_conversation(client, deck_id)
    assert calls == 1
    assert len(state["chapters"]) == 1
    assert state["chapters"][0]["turns"][0]["status"] == "superseded"
    assert state["chapters"][0]["turns"][0]["answer"] is None
    assert state["chapters"][0]["turns"][0]["question"] == "Explain the old list"


@pytest.mark.asyncio
async def test_concurrency_failed_handoff_is_visible_and_not_retried_implicitly(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A summarizer outage leaves archives intact and current-fact answers available."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander, service

    compaction_calls = 0
    observed_handoffs = []

    async def answer(question_input: object) -> TutorAnswerDraft:
        observed_handoffs.append(question_input.handoff)
        return TutorAnswerDraft(content="Current facts remain available.")

    async def failed_compact(_input: object) -> object:
        nonlocal compaction_calls
        compaction_calls += 1
        raise ValueError("deterministic compaction outage")

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", failed_compact)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "First lesson"},
    )
    await _finished_conversation(client, deck_id)
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 1},
    )
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Resume after the edit"},
    )
    state = await _finished_conversation(client, deck_id)
    assert state["chapters"][1]["handoff_status"] == "failed"
    assert state["chapters"][1]["handoff"] is None
    assert state["chapters"][1]["turns"][0]["status"] == "succeeded"
    assert observed_handoffs[-1] is None

    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Continue without a summary"},
    )
    await _finished_conversation(client, deck_id)
    assert compaction_calls == 1


@pytest.mark.asyncio
async def test_concurrency_failed_handoff_has_deduplicated_explicit_retry(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a deliberate retry restarts compaction, including after another context transition."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compaction_calls = 0
    compaction_inputs = []
    retry_entered = asyncio.Event()
    retry_release = asyncio.Event()

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Current-fact answer")

    async def compact(compaction_input: object) -> TutorHandoffDraft:
        nonlocal compaction_calls
        compaction_inputs.append(compaction_input)
        compaction_calls += 1
        if compaction_calls == 1:
            raise ValueError("deterministic first compaction outage")
        retry_entered.set()
        await retry_release.wait()
        return TutorHandoffDraft(content="Explicitly recovered learning goals")

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Original lesson"},
    )
    await _finished_conversation(client, deck_id)
    for question in ("After first edit", "After second edit"):
        await client.patch(
            f"/api/v1/decks/{deck_id}", json={"description": f"Intent for {question}"}
        )
        await client.post(
            f"/api/v1/decks/{deck_id}/tutor/questions",
            json={"request_key": str(uuid4()), "question": question},
        )
        await _finished_conversation(client, deck_id)
    failed = await _conversation(client, deck_id)
    assert len(failed["chapters"]) == 3
    assert failed["chapters"][-1]["handoff_status"] == "failed"
    assert compaction_calls == 1
    chapter_id = failed["chapters"][-1]["id"]

    retry_url = f"/api/v1/decks/{deck_id}/tutor/chapters/{chapter_id}/handoff"
    key = str(uuid4())
    responses = await asyncio.gather(
        *[
            client.post(retry_url, json={"request_key": request_key})
            for request_key in (key, key, str(uuid4()))
        ]
    )
    assert [response.status_code for response in responses] == [200, 200, 200]
    await retry_entered.wait()
    assert compaction_calls == 2
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_handoff_retries WHERE chapter_id=$1", UUID(chapter_id)
        )
        == 1
    )

    continued = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Continue during retry"},
    )
    assert continued.status_code == 200
    await _finished_conversation(client, deck_id)
    retry_release.set()
    for _ in range(30):
        recovered = await _conversation(client, deck_id)
        if recovered["chapters"][-1]["handoff_status"] == "ready":
            break
        await asyncio.sleep(0)
    assert recovered["chapters"][-1]["handoff"] == "Explicitly recovered learning goals"
    assert len(recovered["chapters"][-1]["turns"]) == 2
    assert compaction_inputs[1].previous_handoff is None
    assert [turn.question for turn in compaction_inputs[1].turns] == [
        "Original lesson",
        "After first edit",
    ]
    await client.post(retry_url, json={"request_key": key})
    await asyncio.sleep(0)
    assert compaction_calls == 2


@pytest.mark.asyncio
async def test_concurrency_handoff_retry_recovers_turns_before_empty_immediate_source(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty failed source chapter does not hide older learning from explicit retry."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compaction_inputs = []

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Current-fact answer")

    async def compact(compaction_input: object) -> TutorHandoffDraft:
        compaction_inputs.append(compaction_input)
        if len(compaction_inputs) == 1:
            raise ValueError("deterministic guide-chapter compaction outage")
        return TutorHandoffDraft(content="Recovered the original lesson")

    async def generate(_input: object) -> object:
        return valid_guide()

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(commander, "generate", generate)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Original lesson"},
    )
    await _finished_conversation(client, deck_id)
    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": "Guide chapter"})
    started = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/guides", json={"request_key": str(uuid4())}
    )
    assert started.status_code == 200
    guide = await _finished_guide(client, deck_id)
    assert guide["status"] == "succeeded"

    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": "Question chapter"})
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Continue after the empty chapter"},
    )
    failed = await _finished_conversation(client, deck_id)
    assert [chapter["handoff_status"] for chapter in failed["chapters"]] == [
        "none",
        "failed",
        "failed",
    ]
    assert failed["chapters"][1]["turns"] == []
    assert len(compaction_inputs) == 1

    chapter_id = failed["chapters"][-1]["id"]
    retry = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/chapters/{chapter_id}/handoff",
        json={"request_key": str(uuid4())},
    )
    assert retry.status_code == 200
    for _ in range(30):
        recovered = await _conversation(client, deck_id)
        if recovered["chapters"][-1]["handoff_status"] == "ready":
            break
        await asyncio.sleep(0)
    assert recovered["chapters"][-1]["handoff"] == "Recovered the original lesson"
    assert [turn.question for turn in compaction_inputs[1].turns] == ["Original lesson"]


@pytest.mark.asyncio
async def test_clear_deletes_chapters_turns_and_handoffs_across_an_epoch(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clear removes Tutor history only and a delayed completion cannot restore it."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    async def compact(_input: object) -> TutorHandoffDraft:
        return TutorHandoffDraft(content="Previous learning goals")

    monkeypatch.setattr(service, "run_compaction_agent", compact)
    entered = asyncio.Event()
    release = asyncio.Event()
    delayed = False

    async def answer(_input: object) -> TutorAnswerDraft:
        nonlocal delayed
        if delayed:
            entered.set()
            await release.wait()
        return TutorAnswerDraft(content="Saved answer")

    monkeypatch.setattr(commander, "answer", answer)
    deck_id = await _deck_id(client)
    for question in ("First", "Second"):
        await client.post(
            f"/api/v1/decks/{deck_id}/tutor/questions",
            json={"request_key": str(uuid4()), "question": question},
        )
        await _finished_conversation(client, deck_id)
        if question == "First":
            await client.post(
                f"/api/v1/decks/{deck_id}/cards",
                json={"card_scryfall_id": str(FOREST_SCRYFALL_ID), "quantity": 1},
            )
    reference = await client.post(
        f"/api/v1/decks/{deck_id}/tutor/reference/preview", json={"source": "current"}
    )
    preview_id = reference.json()["data"]["preview_id"]
    assert (
        await client.put(
            f"/api/v1/decks/{deck_id}/tutor/reference", json={"preview_id": preview_id}
        )
    ).status_code == 200

    delayed = True
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Late work"},
    )
    await entered.wait()
    cleared = await client.delete(f"/api/v1/decks/{deck_id}/tutor/conversation")
    assert cleared.status_code == 200
    assert cleared.json()["data"]["chapters"] == []
    release.set()
    for _ in range(20):
        if (
            await db_pool.fetchval(
                "SELECT count(*) FROM tutor_turns WHERE deck_id=$1", UUID(deck_id)
            )
            == 0
        ):
            break
        await asyncio.sleep(0)
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_chapters WHERE deck_id=$1", UUID(deck_id)
        )
        == 0
    )
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_turns WHERE deck_id=$1", UUID(deck_id))
        == 0
    )
    tutor = await client.get(f"/api/v1/decks/{deck_id}/tutor")
    assert tutor.json()["data"]["reference"] is not None

    delayed = False
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Fresh start"},
    )
    fresh = await _finished_conversation(client, deck_id)
    assert len(fresh["chapters"]) == 1
    assert [turn["question"] for turn in fresh["chapters"][0]["turns"]] == ["Fresh start"]


@pytest.mark.asyncio
async def test_concurrency_resume_creates_one_chapter_and_one_handoff(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tabs resuming an edited deck share its new chapter and compaction."""
    from mtg_helper.models.tutor import TutorAnswerDraft, TutorHandoffDraft
    from mtg_helper.services.tutor import commander, service

    compaction_calls = 0

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Current answer")

    async def compact(_input: object) -> TutorHandoffDraft:
        nonlocal compaction_calls
        compaction_calls += 1
        await asyncio.sleep(0)
        return TutorHandoffDraft(content="Shared handoff")

    monkeypatch.setattr(commander, "answer", answer)
    monkeypatch.setattr(service, "run_compaction_agent", compact)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Before edits"},
    )
    await _finished_conversation(client, deck_id)
    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": "New intent"})

    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/decks/{deck_id}/tutor/questions",
                json={"request_key": str(uuid4()), "question": f"Resume {index}"},
            )
            for index in range(2)
        ]
    )
    assert [response.status_code for response in responses] == [200, 200]
    for _ in range(30):
        state = await _conversation(client, deck_id)
        turns = state["chapters"][-1]["turns"]
        if len(turns) == 2 and all(turn["status"] != "running" for turn in turns):
            break
        await asyncio.sleep(0)
    assert len(state["chapters"]) == 2
    assert len(state["chapters"][1]["turns"]) == 2
    assert compaction_calls == 1
    assert state["chapters"][1]["handoff"] == "Shared handoff"


@pytest.mark.asyncio
async def test_persistence_denies_other_owners_and_unauthenticated_history_access(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current deck ownership guards every read, send, and clear operation."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Private answer")

    monkeypatch.setattr(commander, "answer", answer)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Private question"},
    )
    saved = await _finished_conversation(client, deck_id)
    chapter_id = saved["chapters"][0]["id"]
    await create_test_account(client, "Other Conversation Owner")

    for method, path, payload in (
        ("get", f"/api/v1/decks/{deck_id}/tutor/conversation", None),
        (
            "post",
            f"/api/v1/decks/{deck_id}/tutor/questions",
            {"request_key": str(uuid4()), "question": "Steal history"},
        ),
        (
            "post",
            f"/api/v1/decks/{deck_id}/tutor/chapters/{chapter_id}/handoff",
            {"request_key": str(uuid4())},
        ),
        ("delete", f"/api/v1/decks/{deck_id}/tutor/conversation", None),
    ):
        response = await client.request(method, path, json=payload)
        assert response.status_code == 404
        assert "Private question" not in response.text

    from mtg_helper.auth import get_current_account
    from mtg_helper.main import app

    override = app.dependency_overrides.pop(get_current_account)
    try:
        unauthenticated = await client.get(f"/api/v1/decks/{deck_id}/tutor/conversation")
    finally:
        app.dependency_overrides[get_current_account] = override
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_persistence_source_outage_and_hostile_history_remain_untrusted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source gaps are explicit and user/source instructions never become card facts."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services import combo_service
    from mtg_helper.services.tutor import commander
    from tests.tutor_fixtures import HOSTILE_SOURCE_TEXT

    observed = []

    async def outage(*_args: object) -> object:
        raise combo_service.ComboFetchError("deterministic outage")

    async def answer(question_input: object) -> TutorAnswerDraft:
        observed.append(question_input)
        return TutorAnswerDraft(content="Uncertainty: combo coverage is unavailable.")

    monkeypatch.setattr(combo_service, "fetch_combos", outage)
    monkeypatch.setattr(commander, "answer", answer)
    deck_id = await _deck_id(client)
    await client.patch(f"/api/v1/decks/{deck_id}", json={"description": HOSTILE_SOURCE_TEXT})
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={
            "request_key": str(uuid4()),
            "question": HOSTILE_SOURCE_TEXT,
            "card_name": "Not A Real Card",
        },
    )
    state = await _finished_conversation(client, deck_id)
    assert observed[0].selected_card is None
    assert observed[0].selected_card_present is False
    assert any("Combo coverage is unavailable" in item for item in observed[0].evidence.warnings)
    assert state["chapters"][0]["turns"][0]["status"] == "succeeded"

    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Follow up on current facts"},
    )
    await _finished_conversation(client, deck_id)
    assert observed[1].recent_turns[0].question == HOSTILE_SOURCE_TEXT
    assert observed[1].recent_turns[0].answer == "Uncertainty: combo coverage is unavailable."
    assert not hasattr(observed[1], "guide")


@pytest.mark.asyncio
async def test_persistence_schema_reapplication_pruning_and_deletion_retain_constraints(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chapter evidence pins sources, schema reapplication keeps turns, and decks cascade."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.recommendations import source_repository
    from mtg_helper.services.tutor import commander

    async def answer(_input: object) -> TutorAnswerDraft:
        return TutorAnswerDraft(content="Persisted answer")

    monkeypatch.setattr(commander, "answer", answer)
    cards_hash = "a" * 64
    await db_pool.execute(
        "INSERT INTO recommendation_sources (sha256, kind, payload, published_at) "
        "VALUES ($1, 'cards', $2, now() - interval '40 days')",
        cards_hash,
        b"pinned",
    )
    await db_pool.execute(
        "INSERT INTO new_card_catalog_state "
        "(singleton, generation, started_at, published_at, card_count, source_sha256) "
        "VALUES (true, $1, now(), now(), 1, $2)",
        uuid4(),
        cards_hash,
    )
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Retain this evidence"},
    )
    await _finished_conversation(client, deck_id)
    chapter_id = UUID((await _conversation(client, deck_id))["chapters"][0]["id"])
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_chapter_sources WHERE chapter_id=$1 AND source_hash=$2",
            chapter_id,
            cards_hash,
        )
        == 1
    )

    await db_pool.execute("UPDATE new_card_catalog_state SET source_sha256=NULL")
    assert await source_repository.prune(db_pool) == 0
    await db_pool.execute(SCHEMA_PATH.read_text())
    await db_pool.execute(SCHEMA_PATH.read_text())
    assert (await _conversation(client, deck_id))["chapters"][0]["turns"][0]["answer"] == (
        "Persisted answer"
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM recommendation_sources WHERE sha256=$1", cards_hash
        )
        == 1
    )

    assert (await client.delete(f"/api/v1/decks/{deck_id}")).status_code == 204
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_chapters WHERE deck_id=$1", UUID(deck_id)
        )
        == 0
    )
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_turns WHERE deck_id=$1", UUID(deck_id))
        == 0
    )
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor/conversation")).status_code == 404
    assert await source_repository.prune(db_pool) == 1


@pytest.mark.asyncio
async def test_concurrency_interrupted_answer_cannot_complete_later(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Startup recovery marks durable work interrupted and blocks a late publication."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander
    from mtg_helper.services.tutor.repository import interrupt_running

    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed(_input: object) -> TutorAnswerDraft:
        entered.set()
        await release.wait()
        return TutorAnswerDraft(content="Must not publish")

    monkeypatch.setattr(commander, "answer", delayed)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Interrupted question"},
    )
    await entered.wait()
    await interrupt_running(db_pool)
    release.set()
    state = await _finished_conversation(client, deck_id)
    turn = state["chapters"][0]["turns"][0]
    assert turn["status"] == "interrupted"
    assert turn["answer"] is None
    assert "interrupted" in turn["error"].lower()


@pytest.mark.asyncio
async def test_concurrency_external_failure_keeps_question_and_requires_explicit_retry(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed request key cannot secretly retry; a new explicit key can recover."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander

    calls = 0

    async def unreliable(_input: object) -> TutorAnswerDraft:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("deterministic answer outage")
        return TutorAnswerDraft(content="Explicit retry succeeded")

    monkeypatch.setattr(commander, "answer", unreliable)
    deck_id = await _deck_id(client)
    key = str(uuid4())
    payload = {"request_key": key, "question": "Preserve this exact question"}
    await client.post(f"/api/v1/decks/{deck_id}/tutor/questions", json=payload)
    failed = await _finished_conversation(client, deck_id)
    turn = failed["chapters"][0]["turns"][0]
    assert turn["status"] == "failed"
    assert turn["question"] == "Preserve this exact question"
    assert turn["answer"] is None

    duplicate = await client.post(f"/api/v1/decks/{deck_id}/tutor/questions", json=payload)
    assert duplicate.status_code == 200
    await asyncio.sleep(0)
    assert calls == 1
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Preserve this exact question"},
    )
    recovered = await _finished_conversation(client, deck_id)
    assert calls == 2
    assert recovered["chapters"][0]["turns"][-1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_persistence_deck_deletion_blocks_delayed_answer_publication(
    client: AsyncClient, db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deck deletion cascades durable intent and a late model result cannot recreate it."""
    from mtg_helper.models.tutor import TutorAnswerDraft
    from mtg_helper.services.tutor import commander

    entered = asyncio.Event()
    release = asyncio.Event()
    returned = asyncio.Event()

    async def delayed(_input: object) -> TutorAnswerDraft:
        entered.set()
        await release.wait()
        returned.set()
        return TutorAnswerDraft(content="Obsolete answer")

    monkeypatch.setattr(commander, "answer", delayed)
    deck_id = await _deck_id(client)
    await client.post(
        f"/api/v1/decks/{deck_id}/tutor/questions",
        json={"request_key": str(uuid4()), "question": "Delete before answering"},
    )
    await entered.wait()
    assert (await client.delete(f"/api/v1/decks/{deck_id}")).status_code == 204
    release.set()
    await returned.wait()
    for _ in range(20):
        await asyncio.sleep(0)
    assert (
        await db_pool.fetchval("SELECT count(*) FROM tutor_turns WHERE deck_id=$1", UUID(deck_id))
        == 0
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM tutor_chapters WHERE deck_id=$1", UUID(deck_id)
        )
        == 0
    )
    assert (await client.get(f"/api/v1/decks/{deck_id}/tutor/conversation")).status_code == 404

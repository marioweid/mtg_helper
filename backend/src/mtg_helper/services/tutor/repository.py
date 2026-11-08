"""Durable owner-scoped Tutor setup, runs, frozen manifests, and results."""

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.models.tutor import (
    TutorCardFact,
    TutorChapterResponse,
    TutorConversationResponse,
    TutorEvidence,
    TutorGuideDraft,
    TutorMode,
    TutorReference,
    TutorReferenceDifferences,
    TutorReferencePreviewResponse,
    TutorReferenceRequest,
    TutorRunResponse,
    TutorTurnContext,
    TutorTurnResponse,
)
from mtg_helper.services import card_service, import_service
from mtg_helper.services.recommendations.repository import Owner, owned_deck
from mtg_helper.services.tutor import evidence


class TutorError(ValueError):
    """Expected owner-scoped Tutor request failure with an HTTP status."""

    def __init__(
        self, message: str, status: int = 400, code: str = "TUTOR_REQUEST_INVALID"
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class TutorWork:
    """One persisted generation intent safe to execute at most once."""

    id: UUID
    token: UUID
    owner: Owner
    deck_id: UUID
    mode: TutorMode
    manifest: dict[str, object]
    guide_evidence: TutorEvidence
    chapter_id: UUID | None = None
    handoff: str | None = None
    compaction_required: bool = False
    compaction_turns: list[TutorTurnContext] = field(default_factory=list)
    previous_handoff: str | None = None
    compaction_through: UUID | None = None


@dataclass(frozen=True)
class TutorQuestionWork:
    """One durable question intent and its immutable current-list capture."""

    id: UUID
    token: UUID
    owner: Owner
    deck_id: UUID
    chapter_id: UUID
    epoch: int
    mode: TutorMode
    manifest: dict[str, object]
    question_evidence: TutorEvidence
    question: str
    card_name: str | None
    selected_card: TutorCardFact | None
    selected_card_present: bool
    handoff: str | None
    recent_turns: list[TutorTurnContext]
    compaction_required: bool
    compaction_turns: list[TutorTurnContext]
    previous_handoff: str | None
    compaction_through: UUID | None


class TutorRepository:
    """Own capture and publication rules behind a small service-facing interface."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def save_mode(self, owner: Owner, deck_id: UUID, mode: TutorMode) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            await conn.execute(
                """
                INSERT INTO tutor_setups (deck_id, account_id, mode)
                VALUES ($1, $2, $3)
                ON CONFLICT (deck_id) DO UPDATE SET account_id = EXCLUDED.account_id,
                    mode = EXCLUDED.mode, updated_at = now()
                """,
                deck_id,
                owner.account_id,
                mode,
            )

    async def preview_reference(
        self, owner: Owner, deck_id: UUID, request: TutorReferenceRequest
    ) -> TutorReferencePreviewResponse:
        """Capture a private candidate without changing the saved reference or deck."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
            _, actual_cards = await evidence.deck_facts(conn, deck)
            candidate = await _reference_candidate(conn, self.pool, owner, deck, request)
            preview_id = uuid4()
            await conn.execute(
                "DELETE FROM tutor_reference_previews WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            await conn.execute(
                "INSERT INTO tutor_reference_previews (id, deck_id, account_id, snapshot) "
                "VALUES ($1,$2,$3,$4::jsonb)",
                preview_id,
                deck_id,
                owner.account_id,
                candidate.model_dump_json(),
            )
            return TutorReferencePreviewResponse(
                preview_id=preview_id,
                reference=candidate,
                differences=evidence.reference_differences(candidate, actual_cards),
            )

    async def confirm_reference(self, owner: Owner, deck_id: UUID, preview_id: UUID) -> None:
        """Atomically replace a reference with the exact preview and supersede active work."""
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            row = await conn.fetchrow(
                "SELECT snapshot FROM tutor_reference_previews "
                "WHERE id=$1 AND deck_id=$2 AND account_id=$3",
                preview_id,
                deck_id,
                owner.account_id,
            )
            if row is None:
                raise TutorError("Reference preview not found; preview the source again", 404)
            candidate = TutorReference.model_validate(_value(row["snapshot"]))
            await conn.execute(
                "INSERT INTO tutor_references (deck_id, account_id, version, snapshot) "
                "VALUES ($1,$2,$3,$4::jsonb) ON CONFLICT (deck_id) DO UPDATE SET "
                "account_id=EXCLUDED.account_id, version=EXCLUDED.version, "
                "snapshot=EXCLUDED.snapshot, created_at=now()",
                deck_id,
                owner.account_id,
                candidate.version,
                candidate.model_dump_json(),
            )
            await conn.execute(
                "DELETE FROM tutor_reference_previews WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            await _supersede_running(conn, deck_id)

    async def remove_reference(self, owner: Owner, deck_id: UUID) -> None:
        """Remove only the optional reference and make old in-flight advice unpublishable."""
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            await conn.execute("DELETE FROM tutor_references WHERE deck_id=$1", deck_id)
            await conn.execute(
                "DELETE FROM tutor_reference_previews WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            await _supersede_running(conn, deck_id)

    async def create(self, owner: Owner, deck_id: UUID, request_key: UUID) -> TutorWork | None:
        """Persist one explicit intent and immutable capture, reusing an idempotent request key."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
            active = await conn.fetchrow(
                "SELECT teaching_hash FROM tutor_runs WHERE deck_id=$1 AND status='running'",
                deck_id,
            )
            setup = await conn.fetchrow(
                "SELECT mode FROM tutor_setups WHERE deck_id = $1 AND account_id = $2",
                deck_id,
                owner.account_id,
            )
            if setup is None:
                raise TutorError("Choose a Tutor mode before generating a guide", 409)
            previous = await conn.fetchrow(
                "SELECT id, deck_id, token, status, manifest, evidence, mode FROM tutor_runs "
                "WHERE account_id=$1 AND request_key=$2",
                owner.account_id,
                request_key,
            )
            if previous is not None:
                if previous["deck_id"] != deck_id:
                    raise TutorError("Request key already belongs to another deck", 409)
                return None
            if active is not None:
                return None
            manifest, guide_evidence = await evidence.capture(
                conn, deck, self.pool, owner.email, include_sources=False
            )
            mode = setup["mode"]
            current_hash = evidence.teaching_hash(manifest, mode)
            work = TutorWork(
                id=uuid4(),
                token=uuid4(),
                owner=owner,
                deck_id=deck_id,
                mode=mode,
                manifest=manifest,
                guide_evidence=guide_evidence,
            )
            chapter, compaction_turns, previous_handoff, through = await self._question_chapter(
                conn, owner, deck_id, mode, manifest, guide_evidence
            )
            work = replace(
                work,
                chapter_id=chapter["id"],
                handoff=chapter["handoff"],
                compaction_required=chapter["handoff_status"] == "pending",
                compaction_turns=compaction_turns,
                previous_handoff=previous_handoff,
                compaction_through=through,
            )
            await conn.execute(
                """
                INSERT INTO tutor_runs (id, deck_id, account_id, request_key, mode,
                    composition_hash,
                    teaching_hash, manifest, evidence, token)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10)
                """,
                work.id,
                deck_id,
                owner.account_id,
                request_key,
                mode,
                evidence.composition_hash(manifest),
                current_hash,
                json.dumps(manifest),
                guide_evidence.model_dump_json(),
                work.token,
            )
        return await self._capture_evidence(work)

    async def _capture_evidence(self, work: TutorWork) -> TutorWork | None:
        """Attach fallible source evidence after durable manual intent exists."""
        try:
            async with self.pool.acquire() as conn, conn.transaction():
                run = await conn.fetchrow(
                    "SELECT id FROM tutor_runs WHERE id=$1 AND token=$2 "
                    "AND status='running' FOR UPDATE",
                    work.id,
                    work.token,
                )
                if run is None:
                    return None
                deck = await owned_deck(conn, work.owner, work.deck_id, lock=True)
                manifest, guide_evidence = await evidence.capture(
                    conn, deck, self.pool, work.owner.email
                )
                setup = await conn.fetchrow(
                    "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
                    work.deck_id,
                    work.owner.account_id,
                )
                current_mode = setup["mode"] if setup else None
                current = evidence.teaching_hash(manifest, current_mode) if current_mode else ""
                expected = evidence.teaching_hash(work.manifest, work.mode)
                status = "running" if current == expected else "superseded"
                await conn.execute(
                    "UPDATE tutor_runs SET evidence=$3::jsonb, status=$4, finished_at="
                    "CASE WHEN $4='superseded' THEN now() ELSE NULL END, error="
                    "CASE WHEN $4='superseded' THEN 'Deck or Tutor inputs changed during capture.' "
                    "ELSE NULL END WHERE id=$1 AND token=$2 AND status='running'",
                    work.id,
                    work.token,
                    guide_evidence.model_dump_json(),
                    status,
                )
                await self._pin_sources(conn, work.id, guide_evidence)
                return replace(work, guide_evidence=guide_evidence) if status == "running" else None
        except Exception:
            await self._fail_token(work, "Guide evidence capture failed; retry explicitly.")
            return None

    async def publish(self, work: TutorWork, guide: TutorGuideDraft) -> None:
        """Publish only if owner, deck, and captured teaching inputs still match."""
        async with self.pool.acquire() as conn, conn.transaction():
            run = await conn.fetchrow(
                "SELECT id FROM tutor_runs WHERE id=$1 AND token=$2 "
                "AND status='running' FOR UPDATE",
                work.id,
                work.token,
            )
            if run is None:
                return
            deck = await owned_deck(conn, work.owner, work.deck_id, lock=True)
            manifest, _ = await evidence.capture(
                conn, deck, self.pool, work.owner.email, include_sources=False
            )
            setup = await conn.fetchrow(
                "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
                work.deck_id,
                work.owner.account_id,
            )
            current_mode = setup["mode"] if setup is not None else None
            current = evidence.teaching_hash(manifest, current_mode) if current_mode else ""
            expected = evidence.teaching_hash(work.manifest, work.mode)
            status = "succeeded" if current == expected else "superseded"
            await conn.execute(
                "UPDATE tutor_runs SET status=$3, guide=$4::jsonb, finished_at=now(), "
                "error=CASE WHEN $3='superseded' THEN "
                "'Deck or Tutor inputs changed during generation.' ELSE NULL END "
                "WHERE id=$1 AND token=$2 AND status='running'",
                work.id,
                work.token,
                status,
                guide.model_dump_json(),
            )

    async def fail(self, work: TutorWork) -> None:
        """Store a safe terminal error without replacing the last successful guide."""
        await self._fail_token(work, "Guide generation failed; retry explicitly.")

    async def _fail_token(self, work: TutorWork, message: str) -> None:
        """Store a failure only for the original durable execution token."""
        await self.pool.execute(
            "UPDATE tutor_runs SET status='failed', "
            "error=$3, "
            "finished_at=now() WHERE id=$1 AND token=$2 AND status='running'",
            work.id,
            work.token,
            message,
        )

    async def state(
        self, owner: Owner, deck_id: UUID
    ) -> tuple[
        TutorMode | None,
        TutorRunResponse | None,
        TutorRunResponse | None,
        TutorReference | None,
        TutorReferenceDifferences | None,
        list[TutorCardFact],
    ]:
        """Read setup and guide status without changing lifecycle state."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id)
            setup = await conn.fetchrow(
                "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            manifest, current_evidence = await evidence.capture(
                conn, deck, self.pool, owner.email, include_sources=False
            )
            current_hashes = {
                mode: evidence.teaching_hash(manifest, mode) for mode in ("commander", "cedh")
            }
            rows = await conn.fetch(
                "SELECT * FROM tutor_runs WHERE deck_id=$1 AND account_id=$2 "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                deck_id,
                owner.account_id,
            )
            successful_row = await conn.fetchrow(
                "SELECT * FROM tutor_runs WHERE deck_id=$1 AND account_id=$2 "
                "AND status='succeeded' "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                deck_id,
                owner.account_id,
            )
            latest = (
                self._view(rows[0], current_hashes, setup["mode"] if setup else None)
                if rows
                else None
            )
            successful = (
                self._view(successful_row, current_hashes, setup["mode"] if setup else None)
                if successful_row
                else None
            )
            return (
                setup["mode"] if setup else None,
                latest,
                successful,
                current_evidence.reference,
                current_evidence.reference_differences,
                current_evidence.commanders + current_evidence.cards,
            )

    async def create_question(
        self,
        owner: Owner,
        deck_id: UUID,
        request_key: UUID,
        question: str,
        card_name: str | None,
    ) -> TutorQuestionWork | None:
        """Persist one owner question and its chapter before any external model work."""
        if not question.strip():
            raise TutorError("Ask a non-empty Tutor question", 422)
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
            previous = await conn.fetchrow(
                "SELECT deck_id FROM tutor_turns WHERE account_id=$1 AND request_key=$2",
                owner.account_id,
                request_key,
            )
            if previous is not None:
                if previous["deck_id"] != deck_id:
                    raise TutorError("Request key already belongs to another deck", 409)
                return None
            setup = await conn.fetchrow(
                "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            if setup is None:
                raise TutorError("Choose a Tutor mode before asking a question", 409)
            mode = setup["mode"]
            manifest, question_evidence = await evidence.capture(
                conn, deck, self.pool, owner.email, include_sources=False
            )
            (
                chapter,
                compaction_turns,
                previous_handoff,
                compaction_through,
            ) = await self._question_chapter(
                conn, owner, deck_id, mode, manifest, question_evidence
            )
            turn_id = uuid4()
            work = TutorQuestionWork(
                id=turn_id,
                token=uuid4(),
                owner=owner,
                deck_id=deck_id,
                chapter_id=chapter["id"],
                epoch=chapter["epoch"],
                mode=mode,
                manifest=manifest,
                question_evidence=question_evidence,
                question=question.strip(),
                card_name=card_name.strip() if card_name else None,
                selected_card=_selected_card(question_evidence, card_name),
                selected_card_present=_selected_card(question_evidence, card_name) is not None,
                handoff=chapter["handoff"],
                recent_turns=await self._recent_turns(conn, chapter["id"]),
                compaction_required=chapter["handoff_status"] == "pending",
                compaction_turns=compaction_turns,
                previous_handoff=previous_handoff,
                compaction_through=compaction_through,
            )
            await conn.execute(
                "INSERT INTO tutor_turns (id, chapter_id, deck_id, account_id, epoch, "
                "request_key, token, question, card_name, teaching_hash) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                work.id,
                work.chapter_id,
                deck_id,
                owner.account_id,
                work.epoch,
                request_key,
                work.token,
                work.question,
                work.card_name,
                chapter["teaching_hash"],
            )
        return await self._capture_question_evidence(work)

    async def _question_chapter(
        self,
        conn: asyncpg.Connection,
        owner: Owner,
        deck_id: UUID,
        mode: TutorMode,
        manifest: dict[str, object],
        question_evidence: TutorEvidence,
    ) -> tuple[asyncpg.Record, list[TutorTurnContext], str | None, UUID | None]:
        """Reuse only the latest matching chapter; returning to old facts starts fresh."""
        await conn.execute(
            "INSERT INTO tutor_histories (deck_id) VALUES ($1) ON CONFLICT DO NOTHING", deck_id
        )
        history = await conn.fetchrow(
            "SELECT epoch, next_sequence FROM tutor_histories WHERE deck_id=$1 FOR UPDATE", deck_id
        )
        if history is None:
            raise TutorError("Tutor history could not be initialized", 500)
        current_hash = evidence.teaching_hash(manifest, mode)
        latest = await conn.fetchrow(
            "SELECT * FROM tutor_chapters WHERE deck_id=$1 AND epoch=$2 "
            "ORDER BY sequence DESC LIMIT 1",
            deck_id,
            history["epoch"],
        )
        if (
            latest is not None
            and latest["account_id"] == owner.account_id
            and latest["teaching_hash"] == current_hash
        ):
            compaction_turns, through = await self._same_chapter_compaction(conn, latest)
            if compaction_turns:
                await conn.execute(
                    "UPDATE tutor_chapters SET handoff_status='pending', handoff_error=NULL "
                    "WHERE id=$1",
                    latest["id"],
                )
                refreshed = await conn.fetchrow(
                    "SELECT * FROM tutor_chapters WHERE id=$1", latest["id"]
                )
                if refreshed is None:
                    raise TutorError("Tutor chapter could not be reloaded", 500)
                latest = refreshed
            return latest, compaction_turns, latest["handoff"], through
        previous_turns = await self._compaction_turns(conn, latest["id"]) if latest else []
        handoff_status = "pending" if previous_turns else "none"
        handoff_error = None
        if latest is not None and latest["handoff_status"] == "failed":
            handoff_status = "failed"
            handoff_error = "Earlier Lernübergabe unavailable; answers use current facts only."
        chapter_id = uuid4()
        await conn.execute(
            "INSERT INTO tutor_chapters (id, deck_id, account_id, epoch, sequence, mode, "
            "composition_hash, teaching_hash, manifest, evidence, handoff_status, handoff_error) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11,$12)",
            chapter_id,
            deck_id,
            owner.account_id,
            history["epoch"],
            history["next_sequence"],
            mode,
            evidence.composition_hash(manifest),
            current_hash,
            json.dumps(manifest),
            question_evidence.model_dump_json(),
            handoff_status,
            handoff_error,
        )
        await conn.execute(
            "UPDATE tutor_histories SET next_sequence=next_sequence+1 WHERE deck_id=$1", deck_id
        )
        chapter = await conn.fetchrow("SELECT * FROM tutor_chapters WHERE id=$1", chapter_id)
        if chapter is None:
            raise TutorError("Tutor chapter could not be saved", 500)
        return chapter, previous_turns, latest["handoff"] if latest else None, None

    @staticmethod
    async def _same_chapter_compaction(
        conn: asyncpg.Connection, chapter: asyncpg.Record
    ) -> tuple[list[TutorTurnContext], UUID | None]:
        """Compact twelve new turns down to a handoff plus eight recent full turns."""
        if chapter["handoff_status"] not in {"none", "ready"}:
            return [], None
        rows = await conn.fetch(
            "SELECT id, question, answer, created_at FROM tutor_turns "
            "WHERE chapter_id=$1 AND status='succeeded' AND ($2::uuid IS NULL OR "
            "(created_at,id) > (SELECT created_at,id FROM tutor_turns WHERE id=$2)) "
            "ORDER BY created_at DESC, id DESC LIMIT 32",
            chapter["id"],
            chapter["handoff_through"],
        )
        chronological = list(reversed(rows))
        if len(chronological) < 12:
            return [], None
        candidates = chronological[:-8][-24:]
        turns = [
            TutorTurnContext(question=row["question"], answer=row["answer"]) for row in candidates
        ]
        return turns, candidates[-1]["id"]

    @staticmethod
    async def _compaction_turns(
        conn: asyncpg.Connection, chapter_id: UUID
    ) -> list[TutorTurnContext]:
        """Bound archived compaction input while retaining the full transcript for display."""
        rows = await conn.fetch(
            "SELECT question, answer FROM tutor_turns WHERE chapter_id=$1 AND status='succeeded' "
            "ORDER BY created_at DESC, id DESC LIMIT 24",
            chapter_id,
        )
        return [
            TutorTurnContext(question=row["question"], answer=row["answer"])
            for row in reversed(rows)
        ]

    @staticmethod
    async def _recent_turns(conn: asyncpg.Connection, chapter_id: UUID) -> list[TutorTurnContext]:
        rows = await conn.fetch(
            "SELECT question, answer FROM tutor_turns WHERE chapter_id=$1 AND status='succeeded' "
            "ORDER BY created_at DESC, id DESC LIMIT 8",
            chapter_id,
        )
        return [
            TutorTurnContext(question=row["question"], answer=row["answer"])
            for row in reversed(rows)
        ]

    async def _capture_question_evidence(self, work: TutorQuestionWork) -> TutorQuestionWork | None:
        """Refresh fallible sources after the original question is safely durable."""
        try:
            async with self.pool.acquire() as conn, conn.transaction():
                turn = await conn.fetchrow(
                    "SELECT id FROM tutor_turns WHERE id=$1 AND token=$2 AND status='running' "
                    "FOR UPDATE",
                    work.id,
                    work.token,
                )
                if turn is None:
                    return None
                deck = await owned_deck(conn, work.owner, work.deck_id, lock=True)
                manifest, captured = await evidence.capture(conn, deck, self.pool, work.owner.email)
                current = await self._question_still_current(conn, work, manifest)
                if not current:
                    await self._supersede_question(conn, work)
                    return None
                await conn.execute(
                    "UPDATE tutor_chapters SET evidence=$2::jsonb WHERE id=$1",
                    work.chapter_id,
                    captured.model_dump_json(),
                )
                await self._pin_chapter_sources(conn, work.chapter_id, captured)
                return replace(work, question_evidence=captured)
        except Exception:
            await self.fail_question(work)
            return None

    async def _question_still_current(
        self, conn: asyncpg.Connection, work: TutorQuestionWork, manifest: dict[str, object]
    ) -> bool:
        history_epoch = await conn.fetchval(
            "SELECT epoch FROM tutor_histories WHERE deck_id=$1", work.deck_id
        )
        latest_id = await conn.fetchval(
            "SELECT id FROM tutor_chapters WHERE deck_id=$1 AND epoch=$2 "
            "ORDER BY sequence DESC LIMIT 1",
            work.deck_id,
            work.epoch,
        )
        mode = await conn.fetchval(
            "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
            work.deck_id,
            work.owner.account_id,
        )
        return (
            history_epoch == work.epoch
            and latest_id == work.chapter_id
            and mode == work.mode
            and evidence.teaching_hash(manifest, mode)
            == evidence.teaching_hash(work.manifest, work.mode)
        )

    async def start_handoff(self, work: TutorWork | TutorQuestionWork) -> bool:
        """Claim one lazy compaction; overlapping questions never duplicate that model call."""
        if work.chapter_id is None:
            return False
        result = await self.pool.execute(
            "UPDATE tutor_chapters SET handoff_status='running', handoff_error=NULL "
            "WHERE id=$1 AND handoff_status='pending'",
            work.chapter_id,
        )
        return result == "UPDATE 1"

    async def complete_handoff(self, work: TutorWork | TutorQuestionWork, handoff: str) -> None:
        """Retain a bounded summary as untrusted learning context, not current evidence."""
        if work.chapter_id is None:
            return
        await self.pool.execute(
            "UPDATE tutor_chapters SET handoff=$2, handoff_through=$3, "
            "handoff_status='ready', handoff_error=NULL "
            "WHERE id=$1 AND handoff_status='running'",
            work.chapter_id,
            handoff,
            work.compaction_through,
        )

    async def fail_handoff(self, work: TutorWork | TutorQuestionWork) -> None:
        """Expose unavailable compaction while allowing current-fact chat to continue."""
        if work.chapter_id is None:
            return
        await self.pool.execute(
            "UPDATE tutor_chapters SET handoff=NULL, handoff_status='failed', "
            "handoff_error='Lernübergabe failed; this answer uses current deck facts only.' "
            "WHERE id=$1 AND handoff_status='running'",
            work.chapter_id,
        )

    async def publish_question(self, work: TutorQuestionWork, answer: str) -> None:
        """Publish only into the same chapter, history epoch, and exact teaching context."""
        async with self.pool.acquire() as conn, conn.transaction():
            turn = await conn.fetchrow(
                "SELECT id FROM tutor_turns WHERE id=$1 AND token=$2 "
                "AND status='running' FOR UPDATE",
                work.id,
                work.token,
            )
            if turn is None:
                return
            try:
                deck = await owned_deck(conn, work.owner, work.deck_id, lock=True)
                manifest, _ = await evidence.capture(
                    conn, deck, self.pool, work.owner.email, include_sources=False
                )
                current = await self._question_still_current(conn, work, manifest)
            except TutorError:
                current = False
            if current:
                await conn.execute(
                    "UPDATE tutor_turns SET answer=$3, status='succeeded', finished_at=now() "
                    "WHERE id=$1 AND token=$2 AND status='running'",
                    work.id,
                    work.token,
                    answer,
                )
            else:
                await self._supersede_question(conn, work)

    @staticmethod
    async def _supersede_question(conn: asyncpg.Connection, work: TutorQuestionWork) -> None:
        await conn.execute(
            "UPDATE tutor_turns SET status='superseded', finished_at=now(), "
            "error='Deck or Tutor inputs changed during the answer; ask again in the new chapter.' "
            "WHERE id=$1 AND token=$2 AND status='running'",
            work.id,
            work.token,
        )

    async def fail_question(self, work: TutorQuestionWork) -> None:
        """Keep the original question visible with an explicit retryable failure."""
        await self.pool.execute(
            "UPDATE tutor_turns SET status='failed', finished_at=now(), "
            "error='Tutor answer failed; retry explicitly with a new question request.' "
            "WHERE id=$1 AND token=$2 AND status='running'",
            work.id,
            work.token,
        )

    async def clear_conversation(self, owner: Owner, deck_id: UUID) -> None:
        """Advance a deck-wide epoch so no delayed answer can recreate cleared history."""
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, owner, deck_id, lock=True)
            await conn.execute(
                "INSERT INTO tutor_histories (deck_id) VALUES ($1) ON CONFLICT DO NOTHING", deck_id
            )
            await conn.execute("DELETE FROM tutor_chapters WHERE deck_id=$1", deck_id)
            await conn.execute(
                "UPDATE tutor_histories SET epoch=epoch+1, next_sequence=1 WHERE deck_id=$1",
                deck_id,
            )

    async def conversation(self, owner: Owner, deck_id: UUID) -> TutorConversationResponse:
        """Return full owner messages and frozen archives without trusting client history."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id)
            setup = await conn.fetchrow(
                "SELECT mode FROM tutor_setups WHERE deck_id=$1 AND account_id=$2",
                deck_id,
                owner.account_id,
            )
            manifest, _ = await evidence.capture(
                conn, deck, self.pool, owner.email, include_sources=False
            )
            epoch = await conn.fetchval(
                "SELECT epoch FROM tutor_histories WHERE deck_id=$1", deck_id
            )
            if epoch is None:
                return TutorConversationResponse()
            rows = await conn.fetch(
                "SELECT * FROM tutor_chapters WHERE deck_id=$1 AND account_id=$2 AND epoch=$3 "
                "ORDER BY sequence",
                deck_id,
                owner.account_id,
                epoch,
            )
            latest_id = await conn.fetchval(
                "SELECT id FROM tutor_chapters WHERE deck_id=$1 AND epoch=$2 "
                "ORDER BY sequence DESC LIMIT 1",
                deck_id,
                epoch,
            )
            current_hash = (
                evidence.teaching_hash(manifest, setup["mode"]) if setup is not None else ""
            )
            turns = await conn.fetch(
                "SELECT * FROM tutor_turns WHERE deck_id=$1 AND account_id=$2 AND epoch=$3 "
                "ORDER BY created_at, id",
                deck_id,
                owner.account_id,
                epoch,
            )
        by_chapter: dict[UUID, list[TutorTurnResponse]] = {row["id"]: [] for row in rows}
        for row in turns:
            by_chapter[row["chapter_id"]].append(_turn_view(row))
        chapters = [
            TutorChapterResponse(
                id=row["id"],
                sequence=row["sequence"],
                mode=row["mode"],
                teaching_hash=row["teaching_hash"],
                composition_hash=row["composition_hash"],
                manifest=_value(row["manifest"]),
                current=(
                    row["id"] == latest_id
                    and row["mode"] == (setup["mode"] if setup else None)
                    and row["teaching_hash"] == current_hash
                ),
                handoff=row["handoff"],
                handoff_status=row["handoff_status"],
                handoff_error=row["handoff_error"],
                turns=by_chapter[row["id"]],
                created_at=row["created_at"],
            )
            for row in rows
        ]
        return TutorConversationResponse(chapters=chapters)

    @staticmethod
    async def _pin_chapter_sources(
        conn: asyncpg.Connection, chapter_id: UUID, question_evidence: TutorEvidence
    ) -> None:
        source_hashes = _source_hashes(question_evidence.sources)
        present = await conn.fetch(
            "SELECT sha256 FROM recommendation_sources WHERE sha256 = ANY($1::text[])",
            source_hashes,
        )
        await conn.executemany(
            "INSERT INTO tutor_chapter_sources (chapter_id, source_hash) VALUES ($1,$2) "
            "ON CONFLICT DO NOTHING",
            [(chapter_id, row["sha256"]) for row in present],
        )

    @staticmethod
    async def _pin_sources(
        conn: asyncpg.Connection, run_id: UUID, guide_evidence: TutorEvidence
    ) -> None:
        """Retain source snapshots explicitly cited by a saved run."""
        source_hashes = _source_hashes(guide_evidence.sources)
        if not source_hashes:
            return
        present = await conn.fetch(
            "SELECT sha256 FROM recommendation_sources WHERE sha256 = ANY($1::text[])",
            source_hashes,
        )
        await conn.executemany(
            "INSERT INTO tutor_run_sources (run_id, source_hash) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            [(run_id, row["sha256"]) for row in present],
        )

    @staticmethod
    def _view(
        row: asyncpg.Record, current_hashes: dict[str, str], selected_mode: TutorMode | None
    ) -> TutorRunResponse:
        current = (
            row["teaching_hash"] == current_hashes[row["mode"]] and row["mode"] == selected_mode
        )
        return TutorRunResponse(
            id=row["id"],
            status=row["status"],
            mode=row["mode"],
            current=current,
            guide=TutorGuideDraft.model_validate(_value(row["guide"])) if row["guide"] else None,
            evidence=TutorEvidence.model_validate(_value(row["evidence"]))
            if row["evidence"]
            else None,
            error=row["error"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
        )


def _selected_card(question_evidence: TutorEvidence, card_name: str | None) -> TutorCardFact | None:
    """Resolve a client selection against current facts, never client-supplied card data."""
    if card_name is None:
        return None
    normalized = card_name.strip().casefold()
    return next(
        (
            card
            for card in question_evidence.commanders + question_evidence.cards
            if card.name.casefold() == normalized
        ),
        None,
    )


def _turn_view(row: asyncpg.Record) -> TutorTurnResponse:
    return TutorTurnResponse(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        card_name=row["card_name"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


async def _reference_candidate(
    conn: asyncpg.Connection,
    pool: asyncpg.Pool,
    owner: Owner,
    target: asyncpg.Record,
    request: TutorReferenceRequest,
) -> TutorReference:
    """Resolve one source completely and enforce its exact commander configuration."""
    target_commanders, _ = await evidence.deck_facts(conn, target)
    source: Literal["current_deck", "owned_deck", "pasted_text"]
    if request.source == "current":
        source = "current_deck"
    elif request.source == "owned":
        source = "owned_deck"
    else:
        source = "pasted_text"
    source_deck_id: UUID | None = None
    source_name = "Pasted deck list"
    if request.source in {"current", "owned"}:
        if request.source == "owned":
            if request.source_deck_id is None:
                raise TutorError("Choose an owned deck to preview as a reference", 422)
            source_deck_id = request.source_deck_id
        else:
            source_deck_id = target["id"]
        source_deck = await owned_deck(conn, owner, source_deck_id, lock=True)
        commanders, cards = await evidence.deck_facts(conn, source_deck)
        source_name = source_deck["name"]
    else:
        commanders, cards = await _pasted_facts(conn, pool, request.text)
    if _commander_keys(commanders) != _commander_keys(target_commanders):
        raise TutorError(
            "Reference commanders must exactly match the current deck's commander configuration",
            422,
        )
    return TutorReference(
        version=uuid4(),
        source=source,
        source_deck_id=source_deck_id,
        source_name=source_name,
        source_url=request.source_url,
        captured_at=datetime.now(UTC),
        commanders=commanders,
        cards=cards,
    )


async def _pasted_facts(
    conn: asyncpg.Connection, pool: asyncpg.Pool, text: str | None
) -> tuple[list[TutorCardFact], list[TutorCardFact]]:
    """Reuse import parsing/resolution without creating or modifying a physical deck."""
    if not text or not text.strip():
        raise TutorError("Paste a deck list with commanders marked *CMDR*", 422)
    try:
        entries = import_service.parse_deck_list(text)
    except ValueError as exc:
        raise TutorError(str(exc), 422) from exc
    resolved: list[tuple[UUID, int, bool]] = []
    unresolved: list[str] = []
    for entry in entries:
        card = await card_service.resolve_card_by_name(pool, entry.name)
        if card is None:
            unresolved.append(entry.name)
        else:
            resolved.append((card.scryfall_id, entry.quantity, entry.is_commander))
    if unresolved:
        names = ", ".join(dict.fromkeys(unresolved))
        raise TutorError(f"Unresolved reference entries: {names}. Correct them and retry.", 422)
    if not any(entry.is_commander for entry in entries):
        raise TutorError("Mark every reference commander with *CMDR* and retry", 422)
    commanders, cards = await evidence.resolved_facts(conn, resolved)
    if any(commander.quantity != 1 for commander in commanders) or not commanders:
        raise TutorError("A reference must contain each commander exactly once", 422)
    return commanders, cards


def _commander_keys(commanders: list[TutorCardFact]) -> set[str]:
    return {str(card.oracle_id) if card.oracle_id else card.name.casefold() for card in commanders}


async def _supersede_running(conn: asyncpg.Connection, deck_id: UUID) -> None:
    """Make pre-reference-change work terminal without starting any replacement."""
    await conn.execute(
        "UPDATE tutor_runs SET status='superseded', finished_at=now(), "
        "error='The reference changed during generation; update explicitly when ready.' "
        "WHERE deck_id=$1 AND status='running'",
        deck_id,
    )


def _value(raw: object) -> dict[str, object]:
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise TutorError("Stored Tutor data is invalid", 500)
    return dict(value)


def _source_hashes(sources: dict[str, str | None]) -> list[str]:
    """Extract immutable source digests from explicit evidence statuses."""
    return [
        status.rsplit(":", maxsplit=1)[1]
        for status in sources.values()
        if isinstance(status, str) and re.fullmatch(r"pinned-(?:cards|rules):[0-9a-f]{64}", status)
    ]


async def interrupt_running(pool: asyncpg.Pool) -> None:
    """Mark process-lost work interrupted at startup; recovery is always explicit."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE tutor_runs SET status='interrupted', finished_at=now(), "
            "error='Guide generation was interrupted; retry explicitly.' WHERE status='running'"
        )
        await conn.execute(
            "UPDATE tutor_turns SET status='interrupted', finished_at=now(), "
            "error='Tutor answer was interrupted; retry explicitly.' WHERE status='running'"
        )
        await conn.execute(
            "UPDATE tutor_chapters SET handoff_status='failed', handoff=NULL, "
            "handoff_error='Lernübergabe was interrupted; current-fact chat remains available.' "
            "WHERE handoff_status IN ('pending', 'running')"
        )

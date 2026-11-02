"""Durable owner-scoped Tutor setup, runs, frozen manifests, and results."""

import json
import re
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.models.tutor import TutorEvidence, TutorGuideDraft, TutorMode, TutorRunResponse
from mtg_helper.services.recommendations.repository import Owner, owned_deck
from mtg_helper.services.tutor import evidence


class TutorError(ValueError):
    """Expected owner-scoped Tutor request failure with an HTTP status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


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
    ) -> tuple[TutorMode | None, TutorRunResponse | None, TutorRunResponse | None]:
        """Read setup and guide status without changing lifecycle state."""
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
            return (setup["mode"] if setup else None, latest, successful)

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
    await pool.execute(
        "UPDATE tutor_runs SET status='interrupted', finished_at=now(), "
        "error='Guide generation was interrupted; retry explicitly.' WHERE status='running'"
    )

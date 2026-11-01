"""Durable owner-scoped Tutor setup, runs, frozen manifests, and results."""

import json
import re
from dataclasses import dataclass
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
                ON CONFLICT (deck_id) DO UPDATE SET mode = EXCLUDED.mode, updated_at = now()
                """,
                deck_id,
                owner.account_id,
                mode,
            )

    async def create(self, owner: Owner, deck_id: UUID, request_key: UUID) -> TutorWork | None:
        """Persist one explicit intent and immutable capture, reusing an idempotent request key."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id, lock=True)
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
            active = await conn.fetchrow(
                "SELECT teaching_hash FROM tutor_runs WHERE deck_id=$1 AND account_id=$2 "
                "AND status='running'",
                deck_id,
                owner.account_id,
            )
            manifest, guide_evidence = await evidence.capture(conn, deck, self.pool, owner.email)
            mode = setup["mode"]
            current_hash = evidence.teaching_hash(manifest, mode)
            if active is not None and active["teaching_hash"] == current_hash:
                return None
            await conn.execute(
                "UPDATE tutor_runs SET status='superseded', finished_at=now() "
                "WHERE deck_id=$1 AND account_id=$2 AND status='running'",
                deck_id,
                owner.account_id,
            )
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
            source_hashes = _source_hashes(guide_evidence.sources)
            if source_hashes:
                present = await conn.fetch(
                    "SELECT sha256 FROM recommendation_sources WHERE sha256 = ANY($1::text[])",
                    source_hashes,
                )
                await conn.executemany(
                    "INSERT INTO tutor_run_sources (run_id, source_hash) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    [(work.id, row["sha256"]) for row in present],
                )
            return work

    async def publish(self, work: TutorWork, guide: TutorGuideDraft) -> None:
        """Publish only if owner, deck, and captured teaching inputs still match."""
        async with self.pool.acquire() as conn, conn.transaction():
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
        await self.pool.execute(
            "UPDATE tutor_runs SET status='failed', "
            "error='Guide generation failed; retry explicitly.', "
            "finished_at=now() WHERE id=$1 AND token=$2 AND status='running'",
            work.id,
            work.token,
        )

    async def state(
        self, owner: Owner, deck_id: UUID
    ) -> tuple[TutorMode | None, TutorRunResponse | None, TutorRunResponse | None]:
        """Read setup and guide status, marking abandoned execution interrupted once."""
        async with self.pool.acquire() as conn, conn.transaction():
            deck = await owned_deck(conn, owner, deck_id)
            await conn.execute(
                "UPDATE tutor_runs SET status='interrupted', finished_at=now(), "
                "error='Guide generation was interrupted; retry explicitly.' "
                "WHERE deck_id=$1 AND account_id=$2 AND status='running' "
                "AND lease_until <= now()",
                deck_id,
                owner.account_id,
            )
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

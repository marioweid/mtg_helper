"""PostgreSQL-owned single-use attempts, leases and conservative account reservations."""

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

import asyncpg

from mtg_helper.services.recommendations import budget
from mtg_helper.services.recommendations.repository import (
    DiscoveryError,
    Owner,
    owned_deck,
)
from mtg_helper.services.recommendations.source import Card


@dataclass(kw_only=True)
class Work:
    id: UUID
    token: UUID
    owner: Owner
    deck_id: UUID
    source_hash: str
    rules_hash: str
    context: Card
    profile: str = budget.VERSION


@dataclass(kw_only=True)
class NewRun:
    owner: Owner
    deck_id: UUID
    request_key: UUID
    request_hash: str
    source_hash: str
    rules_hash: str
    context: Card
    profile: str = budget.VERSION


async def account_lock(conn: asyncpg.Connection, account_id: UUID) -> None:
    await conn.execute(
        "INSERT INTO recommendation_accounts (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
        account_id,
    )
    await conn.fetchrow(
        "SELECT * FROM recommendation_accounts WHERE account_id = $1 FOR UPDATE",
        account_id,
    )


async def expire_locked(conn: asyncpg.Connection, account_id: UUID) -> None:
    await conn.execute(
        "UPDATE recommendation_runs r SET status = 'interrupted', finished_at = now(), "
        "error = 'Run interrupted; attempted calls are not retried.', "
        "held_microusd = COALESCE((SELECT sum(a.reservation_microusd) "
        "FROM recommendation_attempts a WHERE a.run_id = r.id AND a.cost_microusd IS NULL), 0) "
        "WHERE r.account_id = $1 AND r.status = 'running' AND r.lease_until <= now()",
        account_id,
    )
    await conn.execute(
        "UPDATE recommendation_attempts a SET status = 'unknown' "
        "FROM recommendation_runs r WHERE a.run_id = r.id AND r.account_id = $1 "
        "AND r.status = 'interrupted' AND a.status = 'attempted'",
        account_id,
    )


async def spending(conn: asyncpg.Connection, account_id: UUID) -> int:
    return await conn.fetchval(
        "SELECT COALESCE((SELECT sum(a.cost_microusd) FROM recommendation_attempts a "
        "JOIN recommendation_runs r ON r.id = a.run_id WHERE r.account_id = $1 "
        "AND a.settled_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')), 0) "
        "+ COALESCE((SELECT sum(held_microusd) FROM recommendation_runs WHERE account_id = $1), 0)",
        account_id,
    )


class RunRepository:
    """Serialize claims and settlement under the account lock; never reclaim attempted calls."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def expire(self, owner: Owner) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await account_lock(conn, owner.account_id)
            await expire_locked(conn, owner.account_id)

    async def create(self, new: NewRun) -> tuple[UUID, Work | None]:
        reserved = budget.reservation(new.profile)
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, new.owner, new.deck_id)
            await account_lock(conn, new.owner.account_id)
            await expire_locked(conn, new.owner.account_id)
            existing = await conn.fetchrow(
                "SELECT * FROM recommendation_runs WHERE account_id = $1 AND request_key = $2",
                new.owner.account_id,
                new.request_key,
            )
            if existing:
                if (
                    existing["request_hash"] != new.request_hash
                    or existing["deck_id"] != new.deck_id
                    or existing["profile"] != new.profile
                ):
                    raise DiscoveryError("Request key already used for different inputs", 409)
                return existing["id"], None
            await self._can_create(conn, new)
            run_id, token = uuid4(), uuid4()
            await conn.execute(
                "INSERT INTO recommendation_runs (id, account_id, deck_id, request_key, "
                "request_hash, source_hash, rules_hash, profile, context, token, held_microusd) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)",
                run_id,
                new.owner.account_id,
                new.deck_id,
                new.request_key,
                new.request_hash,
                new.source_hash,
                new.rules_hash,
                new.profile,
                json.dumps(new.context),
                token,
                reserved,
            )
            return run_id, Work(
                id=run_id,
                token=token,
                owner=new.owner,
                deck_id=new.deck_id,
                source_hash=new.source_hash,
                rules_hash=new.rules_hash,
                context=new.context,
                profile=new.profile,
            )

    async def _can_create(self, conn: asyncpg.Connection, new: NewRun) -> None:
        active = await conn.fetchrow(
            "SELECT deck_id FROM recommendation_runs WHERE account_id = $1 AND status = 'running'",
            new.owner.account_id,
        )
        if active:
            raise DiscoveryError("A Discover run is already active; refresh its status", 409)
        unknown = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM recommendation_runs "
            "WHERE account_id = $1 AND status <> 'running' AND held_microusd > 0)",
            new.owner.account_id,
        )
        if unknown:
            raise DiscoveryError("Unknown billing hold; admin reconciliation required", 409)
        if (
            await spending(conn, new.owner.account_id) + budget.reservation(new.profile)
            > budget.DAILY_CAP
        ):
            raise DiscoveryError("Discover daily estimated spending limit reached", 429)

    async def checkpoint(self, work: Work, phase: str, request: Card) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            await owned_deck(conn, work.owner, work.deck_id)
            await account_lock(conn, work.owner.account_id)
            row = await conn.fetchrow(
                "SELECT * FROM recommendation_runs WHERE id = $1 AND token = $2 "
                "AND status = 'running' AND phase = $3 AND lease_until > now() FOR UPDATE",
                work.id,
                work.token,
                phase,
            )
            if row is None or row["profile"] != work.profile:
                return False
            reserved = budget.cost(*budget.bounds(row["profile"])[phase])
            if row["held_microusd"] < reserved:
                raise DiscoveryError("Insufficient reservation; no request sent", 409)
            inserted = await conn.fetchval(
                "INSERT INTO recommendation_attempts "
                "(run_id, phase, request, reservation_microusd) "
                "VALUES ($1,$2,$3::jsonb,$4) ON CONFLICT DO NOTHING RETURNING run_id",
                work.id,
                phase,
                json.dumps(request),
                reserved,
            )
            if inserted is None:
                return False
            await conn.execute(
                "UPDATE recommendation_runs SET lease_until = now() + interval '10 minutes' "
                "WHERE id = $1",
                work.id,
            )
            return True

    async def receipt(self, work: Work, phase: str, receipt: Card, price: int | None) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await account_lock(conn, work.owner.account_id)
            attempt = await conn.fetchrow(
                "SELECT * FROM recommendation_attempts WHERE run_id = $1 AND phase = $2 FOR UPDATE",
                work.id,
                phase,
            )
            if attempt is None or attempt["cost_microusd"] is not None:
                return
            await conn.execute(
                "UPDATE recommendation_attempts SET receipt = $3::jsonb, status = $4, "
                "cost_microusd = $5, settled_at = now() WHERE run_id = $1 AND phase = $2",
                work.id,
                phase,
                json.dumps(receipt),
                "known" if price is not None else "unknown",
                price,
            )
            if price is not None:
                await conn.execute(
                    "UPDATE recommendation_runs SET held_microusd = "
                    "GREATEST(0, held_microusd - $2), "
                    "known_cost_microusd = known_cost_microusd + $3 "
                    "WHERE id = $1",
                    work.id,
                    attempt["reservation_microusd"],
                    price,
                )

    async def publish(self, work: Work, phase: str, data: Card) -> bool:
        next_phase = (
            "done"
            if work.profile == budget.STRATEGY_VERSION
            else {"plan": "revise", "revise": "review", "review": "done"}[phase]
        )
        if phase == "revise" and not data["candidates"]:
            next_phase = "done"
        result = await self.pool.execute(
            "UPDATE recommendation_runs SET data = $3::jsonb, phase = $4, "
            "status = CASE WHEN $4 = 'done' THEN 'completed' ELSE 'running' END, "
            "held_microusd = CASE WHEN $4 = 'done' THEN 0 ELSE held_microusd END, "
            "finished_at = CASE WHEN $4 = 'done' THEN now() ELSE NULL END "
            "WHERE id = $1 AND token = $2 AND status = 'running' AND phase = $5 "
            "AND lease_until > now() AND profile = $6",
            work.id,
            work.token,
            json.dumps(data),
            next_phase,
            phase,
            work.profile,
        )
        return result == "UPDATE 1" and next_phase != "done"

    async def stop(self, work: Work, message: str, *, unknown: bool = False) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await account_lock(conn, work.owner.account_id)
            await conn.execute(
                "UPDATE recommendation_runs r SET status = $3, error = $4, finished_at = now(), "
                "held_microusd = COALESCE((SELECT sum(reservation_microusd) "
                "FROM recommendation_attempts a WHERE a.run_id = r.id "
                "AND a.cost_microusd IS NULL), 0) WHERE id = $1 AND token = $2 "
                "AND status = 'running'",
                work.id,
                work.token,
                "unknown" if unknown else "failed",
                message,
            )

"""Read-only Yuna/Meren diagnostics using the real Discover query; never call a provider."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import asyncpg

from mtg_helper.services.recommendations.profiles_discover_v1 import MATCH_SQL as _MATCH_SQL
from mtg_helper.services.recommendations.source import (
    Catalog,
    build_catalog,
    eligibility_error,
    is_land,
)
from mtg_helper.services.recommendations.strategy_discover import source_terms
from scripts.deck_recovery_check import DECKS, parse_fixture

ROOT = Path(__file__).resolve().parents[2]
EMPTY_ID = UUID(int=0)
# These hypotheses describe roles, not answer identities. Keep them fixed across diagnostic arms.
ROLES = {
    "yuna": [
        "mana-dork",
        "gains-pp-counters",
        "gives-pp-counters",
        "pp-counters-matter",
        "counter-doubler",
        "repeatable-pp-counters",
        "repeatable-proliferate",
    ],
    "meren": [
        "sacrifice-outlet-creature",
        "reanimate-creature",
        "death-trigger",
        "draw-engine",
        "mana-dork",
    ],
}
KEYWORDS = {"yuna": ["Proliferate", "Modular", "Adapt", "Evolve"], "meren": ["Undying", "Persist"]}
GENERIC = {"mana-dork", "draw-engine"}


def local_database(dsn: str) -> str:
    """Refuse anything other than the isolated Compose application database."""
    target = urlsplit(dsn)
    if (
        target.scheme not in {"postgres", "postgresql"}
        or target.hostname != "postgres"
        or target.port not in {None, 5432}
        or target.path != "/mtg_helper"
        or target.query
        or target.fragment
    ):
        raise ValueError("Run with the isolated docker-compose.yml postgres/mtg_helper target")
    return dsn


def score(rows: list[dict[str, Any]], answers: set[str]) -> dict[str, Any]:
    """Measure exact-list recovery without treating off-list alternatives as incorrect."""
    hits = [index for index, row in enumerate(rows, 1) if str(row["oracle_id"]) in answers]
    return {
        "total": len(rows),
        "reference_hits_at_10": sum(rank <= 10 for rank in hits),
        "reference_hits_at_50": sum(rank <= 50 for rank in hits),
        "reference_hits_in_pool": len(hits),
        "target_count": len(answers),
    }


def popularity_probe(rows: list[dict[str, Any]], answers: set[str]) -> dict[str, Any]:
    """Change only tie-breaking, using existing global popularity rather than synergy claims."""
    ranked = sorted(
        rows,
        key=lambda row: (
            -row["match_count"],
            row["edhrec_rank"] is None,
            row["edhrec_rank"] or 0,
            row["name"].lower(),
            str(row["oracle_id"]),
        ),
    )
    return score(ranked, answers) | {
        "cards": [
            {
                "name": row["name"],
                "match_count": row["match_count"],
                "global_rank": row["edhrec_rank"],
                "reference_hit": str(row["oracle_id"]) in answers,
            }
            for row in ranked[:50]
        ]
    }


async def compare(
    conn: asyncpg.Connection,
    leader: dict[str, Any],
    criteria: dict[str, Any],
    answers: set[str],
    *,
    strong_only: bool = False,
) -> dict[str, Any]:
    """Execute production ranking and separately count all eligible reference matches."""
    query = _MATCH_SQL
    if strong_only:
        query = query.replace(
            "/* exact tag identity */", "WHERE m.details->>'weight' IN ('strong','very_strong')"
        )
    arguments = (
        criteria["oracle_tag_ids"],
        criteria["printed_keywords"],
        leader["color_identity"],
        [UUID(leader["oracle_id"])],
        EMPTY_ID,
        EMPTY_ID,
    )
    page = await conn.fetch(query, *arguments, None, None, None, 50)
    pool_query = query.split(", page AS MATERIALIZED (", 1)[0]
    pool_query += (
        " SELECT e.*,c.edhrec_rank FROM eligible e JOIN cards c ON c.id=e.id "
        "ORDER BY e.match_count DESC, lower(e.name), e.oracle_id::text"
    )
    pool = [dict(row) for row in await conn.fetch(pool_query, *arguments)]
    result = score(pool, answers)
    result["criteria"] = criteria
    result["strong_memberships_only"] = strong_only
    result["global_rank_tiebreak"] = popularity_probe(pool, answers)
    result["reference_ranks"] = [
        {"rank": rank, "name": row["name"], "match_count": row["match_count"]}
        for rank, row in enumerate(pool, 1)
        if str(row["oracle_id"]) in answers
    ]
    result["cards"] = [
        {
            "name": row["name"],
            "oracle_id": str(row["oracle_id"]),
            "match_count": row["match_count"],
            "reference_hit": str(row["oracle_id"]) in answers,
            "evidence": json.loads(row["evidence"]),
        }
        for row in page
        if row["oracle_id"] is not None
    ]
    assert page[0]["total"] == result["total"]
    assert [card["oracle_id"] for card in result["cards"]] == [
        str(row["oracle_id"]) for row in pool[:50]
    ]
    return result


async def retrieval(conn: asyncpg.Connection, prose: str, roles: list[str]) -> dict[str, Any]:
    """Check which intended supporting roles the actual bounded term catalog exposes."""
    terms = await source_terms(conn, prose=prose)
    slugs = [tag["slug"] for tag in terms.oracle_tags]
    return {
        "prose": prose,
        "role_positions": {
            slug: slugs.index(slug) + 1 if slug in slugs else None for slug in roles
        },
        "offered_tags": slugs,
        "offered_keywords": terms.printed_keywords,
    }


async def case_report(
    conn: asyncpg.Connection, key: str, catalog: Catalog, tags: dict[str, UUID]
) -> dict[str, Any]:
    """Keep known-good deck identities in scoring only, never in source-term retrieval."""
    commander, brief = DECKS[key]
    leader = catalog.resolve(commander)
    if leader is None:
        raise ValueError(f"{key}: commander missing from the local source")
    main, _ = parse_fixture(
        (ROOT / "backend/evals/deck_recovery" / f"{key}.txt").read_text(encoding="utf-8"),
        commander,
    )
    resolved = [catalog.resolve(name) for _, name in main]
    errors = [
        name
        for (_, name), card in zip(main, resolved, strict=True)
        if eligibility_error(card, set(leader["color_identity"]), leader["oracle_id"])
        not in {None, "land"}
    ]
    if errors or sum(quantity for quantity, _ in main) != 99:
        raise ValueError(f"{key}: invalid or unresolved validation fixture: {errors}")
    answers = {card["oracle_id"] for card in resolved if card is not None and not is_land(card)}
    result = {"commander": commander, "retrieval": await retrieval(conn, brief, ROLES[key])}
    criteria = {
        "oracle_tag_ids": [tags[slug] for slug in ROLES[key]],
        "printed_keywords": KEYWORDS[key],
    }
    result["manual_roles"] = await compare(conn, leader, criteria, answers)
    result["strong_only"] = await compare(conn, leader, criteria, answers, strong_only=True)
    focused = criteria | {
        "oracle_tag_ids": [tags[slug] for slug in ROLES[key] if slug not in GENERIC]
    }
    result["manual_focused_roles"] = await compare(conn, leader, focused, answers)
    saved = await conn.fetchrow(
        "SELECT s.prose,s.queries FROM discover_strategies s "
        "JOIN decks d ON d.id=s.deck_id JOIN cards c ON c.id=d.commander_id "
        "WHERE c.oracle_id=$1 ORDER BY s.updated_at DESC LIMIT 1",
        UUID(leader["oracle_id"]),
    )
    if saved is not None:
        result["saved_retrieval"] = await retrieval(conn, saved["prose"], ROLES[key])
        queries = json.loads(saved["queries"])
        if (
            len(queries) == 1
            and len(queries[0]["groups"]) == 1
            and not queries[0]["card_types_any"]
        ):
            group = queries[0]["groups"][0]
            criteria = {
                "oracle_tag_ids": [UUID(tag) for tag in group["oracle_tag_ids"]],
                "printed_keywords": group["printed_keywords"],
            }
            result["saved"] = await compare(conn, leader, criteria, answers)
        else:
            result["saved_not_flat"] = "Structured searches are not the historical flat baseline"
    return result


async def diagnose() -> dict[str, Any]:
    """Read one consistent local publication without startup, schema writes, or paid calls."""
    conn = await asyncpg.connect(local_database(os.environ["DATABASE_URL"]))
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            state = await conn.fetchrow(
                "SELECT c.source_sha256,t.tag_sha256,c.published_at,c.card_count,t.tag_count "
                "FROM new_card_catalog_state c JOIN scryfall_tag_state t "
                "ON t.source_sha256=c.source_sha256"
            )
            if state is None:
                raise ValueError("Publish matching local card/tag sources before diagnostics")
            facts = await conn.fetch(
                "SELECT n.source_facts FROM new_card_catalog n "
                "JOIN new_card_catalog_state s ON s.generation=n.generation"
            )
            catalog = build_catalog(json.loads(row["source_facts"]) for row in facts)
            tags = {
                row["slug"]: row["id"]
                for row in await conn.fetch("SELECT id,slug FROM scryfall_tags")
            }
            weights = await conn.fetch(
                "SELECT details->>'weight' AS weight,count(*) AS count "
                "FROM scryfall_tag_memberships GROUP BY 1 ORDER BY 1"
            )
            return {
                "source": dict(state),
                "weight_counts": {row["weight"]: row["count"] for row in weights},
                "method": "Read-only production SQL; empty deck exclusions for recovery. "
                "Manual role hypotheses are not model outputs; off-list is not incorrect. "
                "Strong-only filters Oracle memberships, not printed keywords (no strength field).",
                "cases": {key: await case_report(conn, key, catalog, tags) for key in DECKS},
            }
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-saved", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(diagnose())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    for key, case in report["cases"].items():
        for arm in ("saved", "manual_roles", "strong_only", "manual_focused_roles"):
            if arm in case:
                row = case[arm]
                print(
                    f"{key}/{arm}: {row['total']} matches, "
                    f"{row['reference_hits_at_10']} hits@10, "
                    f"{row['reference_hits_at_50']} hits@50, "
                    f"{row['reference_hits_in_pool']}/{row['target_count']} targets reachable"
                )
    if args.check_saved:
        failures = [
            key
            for key, case in report["cases"].items()
            if "saved" in case and case["saved"]["reference_hits_at_50"] < 20
        ]
        if failures:
            raise SystemExit(f"Saved criteria below existing 20-hit recovery target: {failures}")


if __name__ == "__main__":
    main()

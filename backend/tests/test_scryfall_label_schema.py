"""Upgrade the pre-publication schema in a disposable transaction, preserving personal state."""

import asyncpg

from mtg_helper.services.scryfall import _map_card, _upsert_batch
from tests.conftest import SCHEMA_PATH
from tests.test_scryfall_tag_publication import source_cards

_SAVED_STATE_SQL = """
SELECT jsonb_build_object(
    'accounts', (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM accounts a),
    'decks', (SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM decks d),
    'cards', (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM cards c),
    'deck_cards', (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM deck_cards c),
    'plans', (SELECT jsonb_agg(to_jsonb(p) ORDER BY id) FROM deck_card_plans p),
    'feedback', (SELECT jsonb_agg(to_jsonb(f) ORDER BY id) FROM deck_feedback f),
    'preferences', (SELECT jsonb_agg(to_jsonb(p) ORDER BY id) FROM preferences p),
    'collections', (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM collections c),
    'inventory', (SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM collection_cards c),
    'snapshots', (SELECT jsonb_agg(to_jsonb(s) ORDER BY id) FROM deck_snapshots s),
    'snapshot_cards', (SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM deck_snapshot_cards c)
)
"""


async def seed_personal_state(conn: asyncpg.Connection) -> None:
    """Populate intent, deck organization, plans, inventory, feedback, and history."""
    await _upsert_batch(conn, [_map_card(card) for card in source_cards()[:2]])
    cards = await conn.fetch("SELECT id FROM cards ORDER BY name")
    commander, other = cards[0]["id"], cards[1]["id"]
    account = await conn.fetchval(
        "INSERT INTO accounts (display_name, email) VALUES ('Personal User', 'local@example.test') "
        "RETURNING id"
    )
    deck = await conn.fetchval(
        "INSERT INTO decks (name, owner_email, commander_id, description, archetype_tags) "
        "VALUES ('Saved deck', 'local@example.test', $1, 'Keep my description', $2) RETURNING id",
        commander,
        ["moxfield:tokens", "archidekt:graveyard", "storm"],
    )
    collection = await conn.fetchval(
        "INSERT INTO collections (account_id, name) VALUES ($1, 'Personal inventory') RETURNING id",
        account,
    )
    await conn.execute(
        "INSERT INTO collection_cards (collection_id, card_id, quantity, tags) "
        "VALUES ($1, $2, 4, ARRAY['signed copy'])",
        collection,
        other,
    )
    await conn.execute(
        "INSERT INTO deck_cards (deck_id, card_id, quantity, categories, ai_reasoning) "
        "VALUES ($1, $2, 2, ARRAY['My category'], 'Saved explanation')",
        deck,
        other,
    )
    await conn.execute(
        "INSERT INTO deck_card_plans (deck_id, card_id, direction, quantity, categories) "
        "VALUES ($1, $2, 'addition', 3, ARRAY['Personal planned category'])",
        deck,
        commander,
    )
    await conn.execute(
        "INSERT INTO deck_feedback (deck_id, card_id, feedback, reason) "
        "VALUES ($1, $2, 'up', 'Personal feedback')",
        deck,
        other,
    )
    await conn.execute(
        "INSERT INTO preferences (account_id, preference_type, description) "
        "VALUES ($1, 'general', 'My preferences')",
        account,
    )
    snapshot = await conn.fetchval(
        "INSERT INTO deck_snapshots (deck_id, source, stage, deck_name, archetype_tags) "
        "VALUES ($1, 'manual', 'created', 'Saved deck', ARRAY['old intent']) RETURNING id",
        deck,
    )
    await conn.execute(
        "INSERT INTO deck_snapshot_cards (snapshot_id, card_id, quantity, categories) "
        "VALUES ($1, $2, 2, ARRAY['Historical category'])",
        snapshot,
        other,
    )


async def test_additive_tag_schema_upgrade_is_idempotent_and_preserves_user_data(
    db_pool: asyncpg.Pool,
) -> None:
    async with db_pool.acquire() as conn:
        transaction = conn.transaction()
        await transaction.start()
        try:
            await conn.execute("CREATE SCHEMA label_upgrade_fixture")
            await conn.execute("SET LOCAL search_path TO label_upgrade_fixture, public")
            await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            # This slice changes only these tables and the source-kind constraint. Reconstruct
            # their exact pre-publication state; the remaining schema is unchanged from HEAD.
            await conn.execute(
                "DROP TABLE scryfall_tag_state, scryfall_tag_memberships, "
                "scryfall_tag_descendants, scryfall_tags; "
                "ALTER TABLE recommendation_sources DROP CONSTRAINT "
                "recommendation_sources_kind_check; "
                "ALTER TABLE recommendation_sources ADD CONSTRAINT "
                "recommendation_sources_kind_check "
                "CHECK (kind IN ('cards', 'rules'))"
            )
            await seed_personal_state(conn)
            before = await conn.fetchval(_SAVED_STATE_SQL)
            for _ in range(2):
                await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
                assert await conn.fetchval(_SAVED_STATE_SQL) == before
            await conn.execute(
                "INSERT INTO recommendation_sources (sha256, kind, payload) "
                "VALUES ($1, 'oracle_tags', $2)",
                "a" * 64,
                b"source fixture",
            )
            assert await conn.fetchval("SELECT count(*) FROM scryfall_tags") == 0
        finally:
            await transaction.rollback()

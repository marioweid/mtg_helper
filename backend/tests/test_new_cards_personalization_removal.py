"""New Cards uses fresh deck facts, not inactive personalization records."""

from mtg_helper.services.new_cards import repository


async def test_legacy_rows_do_not_change_context_or_reuse_old_assessments(
    pilot, db_pool, model
) -> None:
    """Fresh advice ignores legacy rows and archives a replaced old-context assessment."""
    deck_id, owner, service, _ = pilot
    await service.run(await service.claim(owner, deck_id))

    async with db_pool.acquire() as conn:
        deck = await repository.owned_deck(conn, owner, deck_id)
        initial = await repository.load(conn, owner, deck)
        hashes = {candidate.oracle_id: candidate.input_hash for candidate in initial.candidates}
        old = initial.candidates[0]
        await conn.execute(
            "INSERT INTO deck_coach_memory (deck_id, account_id, notes) VALUES ($1, $2, $3)",
            deck_id,
            owner.account_id,
            "SAVED-MEMORY-SENTINEL",
        )
        await conn.execute(
            "INSERT INTO preferences (account_id, preference_type, description) "
            "VALUES ($1, $2, $3)",
            owner.account_id,
            "general",
            "SAVED-PREFERENCE-SENTINEL",
        )
        await conn.execute(
            "UPDATE new_card_assessments SET input_hash = $4 WHERE deck_id = $1 "
            "AND account_id = $2 AND oracle_id = $3",
            deck_id,
            owner.account_id,
            old.oracle_id,
            "personalized-old-context",
        )
        fresh = await repository.load(conn, owner, deck)

    assert {candidate.oracle_id: candidate.input_hash for candidate in fresh.candidates} == hashes
    assert not fresh.valid(
        next(candidate for candidate in fresh.candidates if candidate.oracle_id == old.oracle_id)
    )
    assert (await service.view(owner, deck_id)).stale

    await service.run(await service.claim(owner, deck_id))

    async with db_pool.acquire() as conn:
        history = await conn.fetchrow(
            "SELECT input_hash FROM new_card_assessment_history WHERE deck_id = $1 "
            "AND account_id = $2 AND oracle_id = $3",
            deck_id,
            owner.account_id,
            old.oracle_id,
        )
    payload = str(model.calls[-1])
    assert history is not None and history["input_hash"] == "personalized-old-context"
    assert "SAVED-MEMORY-SENTINEL" not in payload
    assert "SAVED-PREFERENCE-SENTINEL" not in payload

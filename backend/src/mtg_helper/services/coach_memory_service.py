"""Persistent per-deck memory for MTG Assistant."""

from uuid import UUID

import asyncpg

from mtg_helper.models.ai import CoachMemoryResponse, CommanderCoachRequest, CommanderCoachResponse

_EMPTY_SQL = """
SELECT $1::uuid AS deck_id,
       $2::uuid AS account_id,
       ''::text AS notes,
       NULL::timestamptz AS created_at,
       NULL::timestamptz AS updated_at
"""

_STOP_WORDS = {
    "a",
    "about",
    "all",
    "and",
    "coach",
    "delete",
    "dont",
    "don't",
    "forget",
    "from",
    "i",
    "in",
    "it",
    "like",
    "me",
    "memory",
    "remove",
    "that",
    "the",
    "thing",
    "to",
    "you",
}


def _from_row(row: asyncpg.Record) -> CoachMemoryResponse:
    return CoachMemoryResponse(
        deck_id=row["deck_id"],
        account_id=row["account_id"],
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_memory(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
) -> CoachMemoryResponse:
    """Return existing Coach memory or an empty in-memory default."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT deck_id, account_id, notes, created_at, updated_at
            FROM deck_coach_memory
            WHERE deck_id = $1 AND account_id = $2
            """,
            deck_id,
            account_id,
        )
        if row is None:
            row = await conn.fetchrow(_EMPTY_SQL, deck_id, account_id)
    assert row is not None
    return _from_row(row)


async def upsert_memory(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    notes: str,
) -> CoachMemoryResponse:
    """Create or replace the editable Coach memory notes for a deck."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO deck_coach_memory (deck_id, account_id, notes)
            VALUES ($1, $2, $3)
            ON CONFLICT (deck_id, account_id)
            DO UPDATE SET notes = EXCLUDED.notes, updated_at = now()
            RETURNING deck_id, account_id, notes, created_at, updated_at
            """,
            deck_id,
            account_id,
            notes.strip(),
        )
    assert row is not None
    return _from_row(row)


async def append_memory_note(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    note: str,
) -> CoachMemoryResponse:
    """Append a note unless an identical line is already present."""
    memory = await get_memory(pool, deck_id, account_id)
    clean = note.strip()
    if not clean:
        return memory
    lines = [line.strip() for line in memory.notes.splitlines() if line.strip()]
    if clean.lower() not in {line.lower() for line in lines}:
        lines.append(clean)
    return await upsert_memory(pool, deck_id, account_id, "\n".join(lines))


def remove_memory_by_query(notes: str, query: str) -> tuple[str, list[str]]:
    """Remove lines matching a natural-language delete query."""
    return _remove_matching_lines(notes, query)


def _latest_user_text(message: str) -> str:
    marker = "\nUser:"
    if marker in message:
        return message.rsplit(marker, maxsplit=1)[-1].strip()
    return message.strip()


def _is_show_intent(text: str) -> bool:
    lower = text.lower()
    return "memory" in lower and any(
        phrase in lower for phrase in ("what", "show", "list", "have", "remember")
    )


def _clean_note(note: str) -> str | None:
    cleaned = note.strip(" :.-\n\t")
    lower = cleaned.lower()
    for prefix in ("please ", "pls "):
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip(" :.-\n\t")
            lower = cleaned.lower()
    for suffix in (" please", " pls"):
        if lower.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" :.-\n\t")
            lower = cleaned.lower()
    if lower.startswith("the "):
        cleaned = cleaned[4:].strip()
    return cleaned or None


def _looks_like_memory_note(text: str) -> bool:
    lower = text.lower().strip()
    if lower.endswith("?"):
        return False
    direct_prefixes = (
        "avoid ",
        "don't suggest ",
        "dont suggest ",
        "do not suggest ",
        "i dislike ",
        "i don't like ",
        "i dont like ",
        "i hate ",
        "i like ",
        "i prefer ",
        "i want ",
        "keep ",
        "never suggest ",
        "please don't suggest ",
        "please dont suggest ",
        "please avoid ",
        "preserve ",
        "protect ",
    )
    if lower.startswith(direct_prefixes):
        return True
    if lower.startswith(("for ", "please for ")):
        return any(
            marker in lower
            for marker in (" i want ", " cares about ", " counts ", " means ", " avoid ")
        )
    return " cares about " in lower or " should count as " in lower


def _extract_add_note(text: str, full_message: str) -> str | None:
    lower = text.lower()
    phrases = ("remember that", "remember", "add to memory", "save to memory", "note that")
    for phrase in phrases:
        if phrase in lower:
            start = lower.index(phrase) + len(phrase)
            return _clean_note(text[start:])
    if lower.startswith(("add ", "save ")) and "memory" in full_message.lower():
        return _clean_note(text.split(maxsplit=1)[1])
    if _looks_like_memory_note(text):
        return _clean_note(text)
    return None


def _remove_matching_lines(notes: str, text: str) -> tuple[str, list[str]]:
    words = {
        word.strip(".,:;!?()[]{}\"'").lower()
        for word in text.split()
        if len(word.strip(".,:;!?()[]{}\"'").lower()) >= 3
    }
    keywords = words - _STOP_WORDS
    if not keywords:
        return notes, []
    kept: list[str] = []
    removed: list[str] = []
    for line in notes.splitlines():
        haystack = line.lower()
        if any(keyword in haystack for keyword in keywords):
            removed.append(line)
        else:
            kept.append(line)
    return "\n".join(kept).strip(), removed


def _is_remove_intent(text: str, full_message: str) -> bool:
    lower = text.lower()
    conversation_mentions_memory = "memory" in full_message.lower()
    if "forget" in lower or "delete" in lower or "memory" in lower:
        return True
    return "remove" in lower and (conversation_mentions_memory or "thing" in lower)


async def handle_memory_message(
    pool: asyncpg.Pool,
    deck_id: UUID,
    account_id: UUID,
    request: CommanderCoachRequest,
) -> CommanderCoachResponse | None:
    """Handle conversational memory read/add/remove commands, if present."""
    text = _latest_user_text(request.message)
    memory = await get_memory(pool, deck_id, account_id)

    if _is_show_intent(text):
        if memory.notes:
            reply = f"Here is what I have in memory for this deck:\n\n{memory.notes}"
        else:
            reply = "I don't have any memory notes for this deck yet."
        return CommanderCoachResponse(mode="memory", reply=reply, coach_memory=memory)

    note = _extract_add_note(text, request.message)
    if note is not None:
        current = memory.notes.strip()
        updated_notes = note if not current else f"{current}\n{note}"
        updated = await upsert_memory(pool, deck_id, account_id, updated_notes)
        return CommanderCoachResponse(
            mode="memory",
            reply=(
                f"Saved that to this deck's Assistant memory.\n\nCurrent memory:\n{updated.notes}"
            ),
            coach_memory=updated,
            memory_updated=True,
        )

    if _is_remove_intent(text, request.message):
        updated_notes, removed = _remove_matching_lines(memory.notes, text)
        if not removed:
            return CommanderCoachResponse(
                mode="memory",
                reply="I couldn't find a matching memory note to remove.",
                coach_memory=memory,
            )
        updated = await upsert_memory(pool, deck_id, account_id, updated_notes)
        removed_text = "\n".join(f"- {line}" for line in removed)
        reply = f"Removed this from memory:\n{removed_text}"
        if updated.notes:
            reply += f"\n\nCurrent memory:\n{updated.notes}"
        else:
            reply += "\n\nMemory is now empty."
        return CommanderCoachResponse(
            mode="memory",
            reply=reply,
            coach_memory=updated,
            memory_updated=True,
        )

    return None

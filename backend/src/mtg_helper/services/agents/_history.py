"""Convert client-side chat history into pydantic-ai message objects."""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)


def to_model_messages(history: list[dict[str, str]]) -> list[ModelMessage]:
    """Map ``[{role, content}]`` turns to ``ModelRequest``/``ModelResponse``.

    Args:
        history: Frontend-supplied turns, oldest first. ``role`` is
            ``"user"`` or ``"assistant"``.

    Returns:
        List of pydantic-ai messages suitable for ``Agent.run(message_history=...)``.
        Unknown roles are skipped.
    """
    out: list[ModelMessage] = []
    for turn in history:
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "user":
            out.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            out.append(ModelResponse(parts=[TextPart(content=content)]))
    return out

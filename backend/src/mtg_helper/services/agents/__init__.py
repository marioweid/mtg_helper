"""LLM-driven agents built on pydantic-ai.

Each agent module owns its dependency dataclass, system-prompt builder, and
a public driver coroutine the routers call. Production agents share
``_model.make_openai_model`` so model construction stays consistent.
"""

from mtg_helper.services.agents.commander_suggestor_agent import suggest_turn
from mtg_helper.services.agents.deck_doctor_agent import doctor_deck
from mtg_helper.services.agents.describe_agent import describe_turn
from mtg_helper.services.agents.extract_agent import extract_turn

__all__ = ["describe_turn", "doctor_deck", "extract_turn", "suggest_turn"]

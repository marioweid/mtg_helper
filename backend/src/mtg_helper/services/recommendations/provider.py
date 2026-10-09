"""One bounded Responses request; SDK and application retries are disabled."""

import asyncio

from openai import AsyncOpenAI

from mtg_helper.services.recommendations import budget
from mtg_helper.services.recommendations.source import Card


class Provider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def request(self, frozen: Card) -> Card:
        """Send exactly the checkpointed request, with a total timeout and no tool access."""
        async with AsyncOpenAI(
            api_key=self.api_key, max_retries=0, timeout=budget.TIMEOUT
        ) as client:
            async with asyncio.timeout(budget.TIMEOUT):
                response = await client.responses.create(**frozen)
        return {
            "response_id": response.id,
            "request_id": response._request_id,
            "status": response.status,
            "output": response.output_text,
            "model": response.model,
            "service_tier": response.service_tier,
            "usage": response.usage.model_dump() if response.usage else None,
        }

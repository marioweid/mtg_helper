"""Conservative standard-tier Luna pricing in integer microdollars."""

from typing import Any

MODEL = "gpt-5.6-luna"
VERSION = "app-pilot-v1"
BOUNDS = {"plan": (20_000, 5_000), "revise": (60_000, 5_000), "review": (95_000, 10_000)}
RUN_CAP = 100_000
DAILY_CAP = 1_000_000
TIMEOUT = 300
PRICING_URL = "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md"


def cost(input_tokens: int, output_tokens: int) -> int:
    """Round up $0.25/M cache-write upper input and $1.20/M output, without savings."""
    return (input_tokens * 5 + output_tokens * 24 + 19) // 20


def reservation() -> int:
    """Reserve all three fixed calls; this is not a provider-enforced spending limit."""
    total = sum(cost(*bound) for bound in BOUNDS.values())
    if total > RUN_CAP:
        raise ValueError("Discovery reservation exceeds its run cap")
    return total


def usage_cost(receipt: dict[str, Any], bound: tuple[int, int]) -> int:
    """Stop pricing on unknown tier/model/usage rather than interpreting it as zero."""
    if receipt.get("model") != MODEL or receipt.get("service_tier") != "default":
        raise ValueError("Unknown model/service-tier pricing; spending remains held")
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Unknown usage; spending remains held")
    values = [usage.get("input_tokens"), usage.get("output_tokens")]
    if any(type(v) is not int or not 0 <= v <= maximum for v, maximum in zip(values, bound)):
        raise ValueError("Invalid or oversized usage; spending remains held")
    return cost(values[0], values[1])

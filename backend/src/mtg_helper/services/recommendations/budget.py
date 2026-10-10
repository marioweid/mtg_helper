"""Conservative standard-tier Luna pricing in integer microdollars."""

from typing import Any

MODEL = "gpt-5.6-luna"
VERSION = "app-pilot-v1"
STRATEGY_VERSION = "app-strategy-v2"
STRATEGY_BOUNDS = {"plan": (20_000, 4_000)}
STRATEGY_CAP = 10_000
BOUNDS = {"plan": (20_000, 5_000), "revise": (60_000, 5_000), "review": (95_000, 10_000)}
RUN_CAP = 100_000
DAILY_CAP = 1_000_000
TIMEOUT = 300
PRICING_URL = "https://developers.openai.com/api/docs/models/gpt-5.6-luna.md"


def cost(input_tokens: int, output_tokens: int) -> int:
    """Round up $0.25/M cache-write upper input and $1.20/M output, without savings."""
    return (input_tokens * 5 + output_tokens * 24 + 19) // 20


def bounds(profile: str) -> dict[str, tuple[int, int]]:
    """Return only a known paid protocol's fixed stages; unknown profiles cannot spend."""
    if profile == VERSION:
        return BOUNDS
    if profile == STRATEGY_VERSION:
        return STRATEGY_BOUNDS
    raise ValueError("Unknown Discover spending profile")


def run_cap(profile: str) -> int:
    """Resolve a known protocol's estimate ceiling without changing the shared daily limit."""
    bounds(profile)
    return STRATEGY_CAP if profile == STRATEGY_VERSION else RUN_CAP


def reservation(profile: str = VERSION) -> int:
    """Reserve every fixed call; this is not a provider-enforced spending limit."""
    total = sum(cost(*bound) for bound in bounds(profile).values())
    if total > run_cap(profile):
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

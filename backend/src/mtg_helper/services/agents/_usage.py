"""Safe structured logging for Pydantic AI usage counters."""

import logging
from contextlib import suppress

from pydantic_ai import RunUsage

logger = logging.getLogger(__name__)


def log_run_usage(workflow: str, operation: str, usage: RunUsage) -> None:
    """Log one successful model run without prompts, outputs, or user data."""
    try:
        logger.info(
            "LLM usage workflow=%s operation=%s requests=%d input_tokens=%d "
            "output_tokens=%d cache_read_tokens=%d cache_write_tokens=%d "
            "tool_calls=%d details=%s",
            workflow,
            operation,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            usage.tool_calls,
            dict(sorted(usage.details.items())),
        )
    except Exception:
        # Telemetry must not turn a successful model response into a failed operation.
        with suppress(Exception):
            logger.error("Could not log LLM usage for %s/%s", workflow, operation)

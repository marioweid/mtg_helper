"""Logfire observability setup.

Configuration is centralized here so Logfire is initialized exactly once per
process before framework/client instrumentation is registered.
"""

import logging
from typing import Any

from fastapi import FastAPI

_log = logging.getLogger(__name__)
_CONFIGURED = False


def configure_logfire(app: FastAPI) -> None:
    """Configure Logfire and instrument supported libraries.

    Logfire reads ``LOGFIRE_TOKEN`` from the environment. With
    ``send_to_logfire='if-token-present'`` local development still gets
    OpenTelemetry instrumentation without failing when no token is configured.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    try:
        import logfire
    except ModuleNotFoundError:
        _log.warning("Logfire package is not installed; tracing disabled")
        _CONFIGURED = True
        return

    try:
        configure_kwargs: dict[str, Any] = {"send_to_logfire": "if-token-present"}
        if hasattr(logfire, "MetricsOptions"):
            configure_kwargs["metrics"] = logfire.MetricsOptions(collect_in_spans=True)
        try:
            logfire.configure(service_name="mtg-helper-backend", **configure_kwargs)
        except TypeError:
            configure_kwargs.pop("metrics", None)
            logfire.configure(**configure_kwargs)
        logfire.instrument_fastapi(app)
        logfire.instrument_httpx()
        # Do not instrument asyncpg/Postgres: per-query spans are too dense for
        # normal Coach/API traces and drown out the higher-level operations.
        logfire.instrument_pydantic_ai()
        _CONFIGURED = True
    except Exception:  # noqa: BLE001 - observability must not stop app startup
        _log.exception("Logfire configuration failed; continuing without tracing")

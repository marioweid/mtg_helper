"""Export framework and AI traces to the configured self-hosted Assay instance."""

import asyncio
import logging
from collections.abc import Sequence

# Assay 0.4.0 exposes no public exporter/provider bridge. Keep this private import
# isolated and pin the SDK; its JSON transport is required (protobuf is unsupported).
from assay._exporter import AssaySpanExporter
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult
from pydantic_ai import Agent, InstrumentationSettings

from mtg_helper.config import Settings

_log = logging.getLogger(__name__)


class _ReportingAssayExporter(AssaySpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        result = super().export(spans)
        if result is SpanExportResult.FAILURE:
            # The SDK returns failure silently. Never log payloads or credentials.
            _log.warning(
                "Assay trace export failed; check ASSAY_ENDPOINT connectivity, "
                "ASSAY_API_KEY permissions, and ASSAY_APPLICATION slug"
            )
        return result


def configure_assay(app: FastAPI, settings: Settings) -> TracerProvider | None:
    """Instrument one backend app before its middleware stack is built.

    All three Assay settings are required together; leaving all empty disables
    tracing. Exports run in a background batch worker, never on the request path.
    AI content is captured; HTTP bodies and headers are not explicitly captured.
    """
    existing = getattr(app.state, "assay_provider", None)
    if existing is not None:
        return existing
    endpoint = settings.assay_endpoint.strip()
    api_key = settings.assay_api_key.get_secret_value().strip()
    application = settings.assay_application.strip()
    configured = (endpoint, api_key, application)
    if not any(configured):
        return None
    if not all(configured):
        raise ValueError(
            "Set ASSAY_ENDPOINT, ASSAY_API_KEY, and ASSAY_APPLICATION together, "
            "or leave all three empty to disable tracing"
        )

    exporter = _ReportingAssayExporter(endpoint, api_key)
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "mtg-helper-backend", "assay.application.slug": application}
        )
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    try:
        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=provider, exclude_spans=["receive", "send"]
        )
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        Agent.instrument_all(
            InstrumentationSettings(
                tracer_provider=provider,
                include_content=True,
                include_binary_content=False,
                # v3 uses the standard GenAI agent/tool attributes Assay reads.
                version=3,
                # Assay sums model usage; don't count it again on parent agent spans.
                use_aggregated_usage_attribute_names=True,
            )
        )
    except Exception:
        FastAPIInstrumentor.uninstrument_app(app)
        HTTPXClientInstrumentor().uninstrument()
        Agent.instrument_all(False)
        provider.shutdown()
        raise
    app.state.assay_provider = provider
    _log.info("Assay tracing enabled for application %s", application)
    return provider


async def shutdown_assay(app: FastAPI) -> None:
    """Drain queued traces and close the exporter off the event loop on shutdown."""
    provider = getattr(app.state, "assay_provider", None)
    if provider is None:
        return
    app.state.assay_provider = None
    Agent.instrument_all(False)
    HTTPXClientInstrumentor().uninstrument()
    FastAPIInstrumentor.uninstrument_app(app)
    await asyncio.to_thread(provider.shutdown)

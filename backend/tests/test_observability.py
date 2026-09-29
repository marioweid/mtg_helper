"""Assay export contracts without a database, real model, or remote collector."""

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from assay.exceptions import AssayConfigurationError
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from mtg_helper import observability
from mtg_helper.config import Settings

pytestmark = pytest.mark.no_db
Collector = tuple[str, list[dict[str, Any]]]


def _settings(**values: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://unused",
        openai_api_key="test",
        assay_endpoint=values.get("endpoint", ""),
        assay_api_key=values.get("api_key", ""),
        assay_application=values.get("application", ""),
    )


@pytest.fixture
def collector(request: pytest.FixtureRequest) -> Iterator[Collector]:
    received: list[dict[str, Any]] = []
    status, response = getattr(request, "param", (200, b"{}"))

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                {"path": self.path, "headers": dict(self.headers), "body": json.loads(payload)}
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_settings_load_assay_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSAY_ENDPOINT", "http://assay.test:8080")
    monkeypatch.setenv("ASSAY_API_KEY", "asy_secret")
    monkeypatch.setenv("ASSAY_APPLICATION", "mtg-helper")
    settings = Settings(_env_file=None, database_url="unused", openai_api_key="test")
    assert settings.assay_endpoint == "http://assay.test:8080"
    assert settings.assay_api_key.get_secret_value() == "asy_secret"
    assert settings.assay_application == "mtg-helper"
    assert "asy_secret" not in repr(settings)


async def test_unconfigured_tracing_is_disabled() -> None:
    app = FastAPI()
    assert observability.configure_assay(app, _settings()) is None
    await observability.shutdown_assay(app)
    assert not app.user_middleware


@pytest.mark.parametrize(
    "values",
    [
        {"endpoint": "http://assay.test"},
        {"api_key": "asy_secret"},
        {"application": "mtg"},
        {"endpoint": "http://assay.test", "api_key": "asy_secret"},
        {"endpoint": "http://assay.test", "application": "mtg"},
        {"api_key": "asy_secret", "application": "mtg"},
    ],
)
def test_partial_configuration_fails_with_actionable_error(values: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="ASSAY_ENDPOINT, ASSAY_API_KEY, and ASSAY_APPLICATION"):
        observability.configure_assay(FastAPI(), _settings(**values))


def _attributes(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {item["key"]: next(iter(item["value"].values())) for item in items}


async def test_request_model_tool_and_http_spans_export_to_assay(collector: Collector) -> None:
    endpoint, received = collector
    app = FastAPI()
    settings = _settings(endpoint=endpoint, api_key="asy_secret", application="mtg-helper")
    provider = observability.configure_assay(app, settings)
    assert observability.configure_assay(app, settings) is provider
    agent = Agent(TestModel(), name="tracing-test")

    @agent.tool_plain
    def lookup() -> str:
        return "Sol Ring"

    @app.get("/answer")
    async def answer() -> dict[str, str]:
        async with httpx.AsyncClient() as client:
            await client.get(endpoint + "/upstream")
        result = await agent.run("Suggest a mana rock")
        return {"answer": result.output}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.get("/answer")
        assert response.status_code == 200
    finally:
        # Shutdown must drain queued spans, not discard the final request.
        await observability.shutdown_assay(app)
        await observability.shutdown_assay(app)

    assert received
    spans = []
    for request in received:
        assert request["path"] == "/v1/traces"
        assert request["headers"]["x-api-key"] == "asy_secret"
        assert request["headers"]["Content-Type"] == "application/json"
        for resource in request["body"]["resourceSpans"]:
            attrs = _attributes(resource["resource"]["attributes"])
            assert attrs["assay.application.slug"] == "mtg-helper"
            assert attrs["service.name"] == "mtg-helper-backend"
            for scope in resource["scopeSpans"]:
                spans.extend(scope["spans"])
    assert len({span["traceId"] for span in spans}) == 1
    assert sum(span["kind"] == 2 for span in spans) == 1
    assert any(span["kind"] == 3 for span in spans)
    tool = next(s for s in spans if "lookup" in s["name"])
    assert _attributes(tool["attributes"])["gen_ai.tool.call.result"] == "Sol Ring"
    model_spans = [s for s in spans if "gen_ai.input.messages" in _attributes(s["attributes"])]
    assert model_spans
    assert "Suggest a mana rock" in json.dumps(model_spans)
    assert "Sol Ring" in json.dumps(model_spans)
    assert any("gen_ai.usage.input_tokens" in _attributes(s["attributes"]) for s in model_spans)
    agent_span = next(s for s in spans if s["name"].startswith("invoke_agent"))
    assert "gen_ai.usage.input_tokens" not in _attributes(agent_span["attributes"])
    assert "asy_secret" not in json.dumps(spans)
    # Export traffic must not recursively create more spans.
    assert not any("/v1/traces" in json.dumps(span) for span in spans)


def test_settings_load_assay_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("ASSAY_ENDPOINT", "ASSAY_API_KEY", "ASSAY_APPLICATION"):
        monkeypatch.delenv(variable, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "ASSAY_ENDPOINT=http://assay.test:8080\n"
        "ASSAY_API_KEY=asy_dotenv\nASSAY_APPLICATION=mtg-helper\n"
    )
    settings = Settings(_env_file=dotenv, database_url="unused", openai_api_key="test")
    assert settings.assay_endpoint == "http://assay.test:8080"
    assert settings.assay_api_key.get_secret_value() == "asy_dotenv"
    assert settings.assay_application == "mtg-helper"


@pytest.mark.parametrize("endpoint", ["ftp://assay.test", "http://assay.test/wrong-path"])
def test_invalid_endpoint_fails_before_instrumentation(endpoint: str) -> None:
    app = FastAPI()
    with pytest.raises(AssayConfigurationError, match="endpoint"):
        observability.configure_assay(
            app, _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")
        )
    assert not app.user_middleware


@pytest.mark.parametrize(
    "collector",
    [
        (401, b"{}"),
        (503, b"{}"),
        (200, b'{"partialSuccess":{"rejectedSpans":"1"}}'),
        (200, b"not-json"),
    ],
    indirect=True,
)
async def test_export_rejection_is_nonfatal_and_reported(
    collector: Collector, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint, received = collector
    app = FastAPI()
    observability.configure_assay(
        app, _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")
    )
    try:
        result = await Agent(TestModel()).run("test")
        assert result.output
    finally:
        await observability.shutdown_assay(app)
    assert received
    assert "Assay trace export failed" in caplog.text
    assert "asy_secret" not in caplog.text


async def test_network_failure_does_not_break_agent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def offline(*args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", offline)
    app = FastAPI()
    observability.configure_assay(
        app, _settings(endpoint="http://assay.test", api_key="asy_secret", application="mtg")
    )
    try:
        result = await Agent(TestModel()).run("test")
        assert result.output
    finally:
        await observability.shutdown_assay(app)
    assert "Assay trace export failed" in caplog.text
    assert "asy_secret" not in caplog.text


async def test_startup_failure_drains_traces(
    monkeypatch: pytest.MonkeyPatch, collector: Collector
) -> None:
    from mtg_helper import main

    async def unavailable_database(url: str) -> None:
        raise ConnectionError("database offline")

    monkeypatch.setattr(main, "create_pool", unavailable_database)
    endpoint, received = collector
    app = FastAPI()
    provider = observability.configure_assay(
        app, _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")
    )
    assert provider is not None
    with provider.get_tracer("test").start_as_current_span("startup"):
        pass
    with pytest.raises(ConnectionError, match="database offline"):
        async with main.lifespan(app):
            raise AssertionError("startup should fail")
    assert received
    assert app.state.assay_provider is None


async def test_concurrent_requests_and_errors_keep_separate_traces(collector: Collector) -> None:
    endpoint, received = collector
    app = FastAPI()
    observability.configure_assay(
        app, _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")
    )
    agent = Agent(TestModel())

    @app.get("/answer/{prompt}")
    async def answer(prompt: str) -> dict[str, str]:
        await asyncio.sleep(0)
        if prompt == "fail":
            raise RuntimeError("synthetic failure")
        return {"answer": (await agent.run(prompt)).output}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                *(client.get(f"/answer/{prompt}") for prompt in ("one", "two", "fail"))
            )
        assert [response.status_code for response in responses] == [200, 200, 500]
    finally:
        await observability.shutdown_assay(app)
    spans = [
        span
        for request in received
        for resource in request["body"]["resourceSpans"]
        for scope in resource["scopeSpans"]
        for span in scope["spans"]
    ]
    roots = [span for span in spans if "parentSpanId" not in span]
    assert len(roots) == 3
    assert len({span["traceId"] for span in roots}) == 3
    failed = next(span for span in roots if span["status"]["code"] == 2)
    assert any(event["name"] == "exception" for event in failed["events"])
    model_spans = [s for s in spans if "gen_ai.input.messages" in _attributes(s["attributes"])]
    assert len(model_spans) == 2
    assert len({span["traceId"] for span in model_spans}) == 2
    assert all(span["traceId"] != failed["traceId"] for span in model_spans)


async def test_export_with_active_http_instrumentation_does_not_recurse(
    collector: Collector,
) -> None:
    endpoint, received = collector
    app = FastAPI()
    provider = observability.configure_assay(
        app, _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")
    )
    assert provider is not None
    try:
        with provider.get_tracer("test").start_as_current_span("one-span"):
            pass
        assert await asyncio.to_thread(provider.force_flush)
        assert len(received) == 1
        assert await asyncio.to_thread(provider.force_flush)
        assert len(received) == 1
    finally:
        await observability.shutdown_assay(app)
    assert len(received) == 1


async def test_instrumentation_failure_cleans_up_and_can_retry(
    monkeypatch: pytest.MonkeyPatch, collector: Collector
) -> None:
    endpoint, received = collector
    app = FastAPI()
    settings = _settings(endpoint=endpoint, api_key="asy_secret", application="mtg")

    def unavailable_instrumentation(instrument: object = True) -> None:
        if instrument is not False:
            raise RuntimeError("instrumentation failed")

    with monkeypatch.context() as patch:
        patch.setattr(Agent, "instrument_all", unavailable_instrumentation)
        with pytest.raises(RuntimeError, match="instrumentation failed"):
            observability.configure_assay(app, settings)
    assert not app.user_middleware
    assert getattr(app.state, "assay_provider", None) is None
    observability.configure_assay(app, settings)
    try:
        assert (await Agent(TestModel()).run("retry")).output
    finally:
        await observability.shutdown_assay(app)
    assert received

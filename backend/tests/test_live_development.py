"""Live-data startup and destructive-test safety without external connections."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from mtg_helper import main
from mtg_helper.config import Settings
from tests import conftest

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize("maintenance", [False, True])
async def test_startup_maintenance_is_explicit(
    monkeypatch: pytest.MonkeyPatch, maintenance: bool
) -> None:
    pool = AsyncMock()
    pool.fetchval.return_value = 1
    create = AsyncMock(return_value=pool)
    close = AsyncMock()
    schema = AsyncMock()
    repair = AsyncMock()
    catalogs = AsyncMock()
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(database_url="unused", run_startup_maintenance=maintenance),
    )
    monkeypatch.setattr(main, "create_pool", create)
    monkeypatch.setattr(main, "close_pool", close)
    monkeypatch.setattr(main, "apply_schema", schema)
    monkeypatch.setattr(main.oracle_duplicate_repair_service, "repair_active_decks", repair)
    monkeypatch.setattr(main, "_ensure_theme_catalogs", catalogs)

    async with main._application_lifespan(FastAPI()) as _:
        create.assert_awaited_once_with("unused")
        assert schema.await_count == int(maintenance)
        assert repair.await_count == int(maintenance)
        assert catalogs.await_count == int(maintenance)
        assert pool.fetchval.await_count == (2 if maintenance else 0)
        close.assert_not_awaited()
    close.assert_awaited_once_with(pool)


async def test_pool_closes_when_startup_maintenance_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(
        main, "settings", SimpleNamespace(database_url="unused", run_startup_maintenance=True)
    )
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(main, "close_pool", close)
    monkeypatch.setattr(main, "apply_schema", AsyncMock(side_effect=RuntimeError("schema failure")))
    with pytest.raises(RuntimeError, match="schema failure"):
        async with main._application_lifespan(FastAPI()):
            pytest.fail("Startup must fail before serving requests")
    close.assert_awaited_once_with(pool)


def test_startup_maintenance_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_STARTUP_MAINTENANCE", raising=False)
    values = {"database_url": "unused", "openai_api_key": "test"}
    assert Settings(_env_file=None, **values).run_startup_maintenance is True
    monkeypatch.setenv("RUN_STARTUP_MAINTENANCE", "false")
    assert Settings(_env_file=None, **values).run_startup_maintenance is False


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://mtg:do-not-display@192.0.2.10:5432/mtg_app",
        "postgresql://mtg:do-not-display@192.0.2.10:5432/mtg_helper_test",
        "postgresql://mtg:do-not-display@postgres:5432/mtg_helper",
        "postgresql://mtg:do-not-display@postgres:5432/mtg_helper_test?host=192.0.2.10",
        "postgresql://mtg:do-not-display@postgres:5432/mtg_helper_test?dbname=mtg_app",
        "postgresql://mtg:do-not-display@/mtg_helper_test",
        "not a database URL",
        "",
        "postgresql://mtg:do-not-display@postgres:invalid/mtg_helper_test",
    ],
)
async def test_unsafe_test_database_fails_before_connect(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    connect = AsyncMock()
    monkeypatch.setattr(conftest, "TEST_DB_URL", url)
    monkeypatch.setattr(conftest.asyncpg, "connect", connect)
    with pytest.raises(ValueError, match="TEST_DATABASE_URL") as error:
        await conftest._setup_schema()
    assert "do-not-display" not in str(error.value)
    connect.assert_not_awaited()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "postgres"])
async def test_disposable_local_database_is_accepted(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    url = f"postgresql://mtg:test@{host}:5432/mtg_helper_test"
    connection = AsyncMock()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setenv("DATABASE_URL", "postgresql://mtg:test@postgres:5432/mtg_helper")
    monkeypatch.setattr(conftest, "TEST_DB_URL", url)
    monkeypatch.setattr(conftest.asyncpg, "connect", connect)
    await conftest._setup_schema()
    connect.assert_awaited_once_with(dsn=url)
    connection.close.assert_awaited_once()


async def test_application_database_is_not_a_test_target(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql://mtg:test@localhost:5432/mtg_helper_test"
    connect = AsyncMock()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(conftest, "TEST_DB_URL", url)
    monkeypatch.setattr(conftest.asyncpg, "connect", connect)
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        await conftest._setup_schema()
    connect.assert_not_awaited()

"""Application configuration loaded from environment variables."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = Field(repr=False)
    app_env: Literal["local", "live", "staging", "production"] = "production"
    local_dev_auth: bool = False
    local_dev_account_id: UUID | None = None
    run_startup_maintenance: bool = True
    openai_api_key: Annotated[SecretStr, Field(min_length=1)]
    scryfall_bulk_data_url: str = "https://api.scryfall.com/bulk-data"
    moxfield_base_url: str = "https://api2.moxfield.com"
    moxfield_binder_page_delay_seconds: float = 0.25
    archidekt_base_url: str = "https://archidekt.com/api"

    # Remote Assay tracing is disabled unless all three values are supplied.
    assay_endpoint: str = ""
    assay_api_key: SecretStr = SecretStr("")
    assay_application: str = ""

    # Google Sign-In stays required unless isolated local identity is explicitly enabled.
    google_oauth_client_id: str = ""
    admin_emails: Annotated[list[str], NoDecode] = []

    # Shared secret for internal service-to-service calls (e.g. cron container
    # hitting admin endpoints). Empty disables internal-token auth.
    internal_api_token: str = Field(default="", repr=False)

    # Feature flags: env default; admins override per-global/per-account at
    # runtime via the admin API. The optimizer ships off — its search runs
    # hundreds of CPU-bound simulations, too heavy for the small prod VM to
    # serve concurrently. See services/feature_flag_service.py.
    enable_optimizer: bool = False

    @field_validator("local_dev_account_id", mode="before")
    @classmethod
    def _empty_local_account(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _validate_local_identity(self) -> Self:
        self.assert_local_identity()
        return self

    def assert_local_identity(self) -> None:
        """Refuse local identity outside the exact isolated Compose application database."""
        if not self.local_dev_auth:
            return
        if not self._isolated_local_target():
            raise ValueError(
                "Local identity is allowed only with the isolated local Compose database"
            )
        if self.local_dev_account_id is None:
            raise ValueError("Set LOCAL_DEV_ACCOUNT_ID to an existing local account UUID")

    def _isolated_local_target(self) -> bool:
        target = urlsplit(self.database_url)
        return (
            self.app_env == "local"
            and target.scheme in {"postgres", "postgresql"}
            and target.hostname == "postgres"
            and (target.port or 5432) == 5432
            and target.path == "/mtg_helper"
            and not target.query
            and not target.fragment
        )

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_admin_emails(cls, v: object) -> object:
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v


settings = Settings()

"""Application configuration loaded from environment variables."""

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    gemini_api_key: str = ""
    scryfall_bulk_data_url: str = "https://api.scryfall.com/bulk-data"
    mtgjson_all_printings_url: str = "https://mtgjson.com/api/v5/AllPrintings.json.zip"
    mtgjson_keywords_url: str = "https://mtgjson.com/api/v5/Keywords.json"
    moxfield_base_url: str = "https://api2.moxfield.com"
    moxfield_hub_delay_seconds: float = 5.0
    moxfield_hub_stale_after_hours: float = 168.0
    archidekt_base_url: str = "https://archidekt.com/api"
    archidekt_tag_delay_seconds: float = 1.0
    archidekt_tag_stale_after_hours: float = 168.0

    # LLM
    chat_model: str = "gemini-3.5-flash"
    fast_model: str = "gemini-3.1-flash-lite"

    # Pagination defaults
    default_limit: int = 20
    max_limit: int = 100

    # Google Sign-In. Empty client id disables auth (dev/test only).
    google_oauth_client_id: str = ""
    admin_emails: Annotated[list[str], NoDecode] = []

    # Shared secret for internal service-to-service calls (e.g. cron container
    # hitting admin endpoints). Empty disables internal-token auth.
    internal_api_token: str = ""

    # Feature flags: env default; admins override per-global/per-account at
    # runtime via the admin API. The optimizer ships off — its search runs
    # hundreds of CPU-bound simulations, too heavy for the small prod VM to
    # serve concurrently. See services/feature_flag_service.py.
    enable_optimizer: bool = False

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_admin_emails(cls, v: object) -> object:
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v


settings = Settings()

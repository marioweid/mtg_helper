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
    edhrec_base_url: str = "https://json.edhrec.com/pages/commanders"

    # Qdrant vector search
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "mtg_cards"

    # LLM
    chat_model: str = "gemini-2.5-flash"

    # Embeddings
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100

    # Pagination defaults
    default_limit: int = 20
    max_limit: int = 100

    # Google Sign-In. Empty client id disables auth (dev/test only).
    google_oauth_client_id: str = ""
    admin_emails: Annotated[list[str], NoDecode] = []

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_admin_emails(cls, v: object) -> object:
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v


settings = Settings()

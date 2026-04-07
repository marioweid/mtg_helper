"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openai_api_key: str = ""
    scryfall_bulk_data_url: str = "https://api.scryfall.com/bulk-data"

    # Qdrant vector search
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "mtg_cards"

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100

    # Pagination defaults
    default_limit: int = 20
    max_limit: int = 100


settings = Settings()

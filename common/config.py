from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://inventory:inventory@localhost:5433/inventory"
    test_database_url: str = "postgresql+asyncpg://inventory:inventory@localhost:5433/inventory_test"
    redis_url: str = "redis://localhost:6379/0"
    api_port: int = 8080


@lru_cache
def get_settings() -> Settings:
    return Settings()

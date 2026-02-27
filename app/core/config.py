from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Survivor Fantasy Tracker"
    debug: bool = False

    # Database
    database_url: str = "postgresql://localhost:5432/survivor_fantasy"

    # JWT
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Commissioner registration key
    commissioner_key: str = "changeme"

    # Anthropic API (for AI-assisted scoring)
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()

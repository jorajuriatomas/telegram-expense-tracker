from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_service_host: str = Field(alias="BOT_SERVICE_HOST")
    bot_service_port: int = Field(alias="BOT_SERVICE_PORT")
    database_url: str = Field(alias="DATABASE_URL")
    llm_provider: str = Field(alias="LLM_PROVIDER")
    llm_model_name: str = Field(alias="LLM_MODEL_NAME")
    llm_api_key: str = Field(alias="LLM_API_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

import os
from collections.abc import Iterator

import pytest

from app.core.config import get_settings

_ENV_KEYS = (
    "BOT_SERVICE_HOST",
    "BOT_SERVICE_PORT",
    "DATABASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL_NAME",
    "LLM_API_KEY",
)

_ENV_DEFAULTS = {
    "BOT_SERVICE_HOST": "0.0.0.0",
    "BOT_SERVICE_PORT": "8000",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/expenses",
    "LLM_PROVIDER": "openai",
    "LLM_MODEL_NAME": "gpt-4o-mini",
    "LLM_API_KEY": "test-key",
}

for key, value in _ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)


@pytest.fixture(autouse=True)
def settings_env() -> Iterator[None]:
    previous_values = {key: os.environ.get(key) for key in _ENV_KEYS}

    for key, value in _ENV_DEFAULTS.items():
        os.environ[key] = value
    get_settings.cache_clear()

    yield

    for key, value in previous_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()

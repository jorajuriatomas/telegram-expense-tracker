import asyncio
from typing import Any

from app.infrastructure.postgres.whitelist_repository import PostgresWhitelistRepository


class FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    def __init__(self, scalar_value: Any) -> None:
        self._scalar_value = scalar_value
        self.last_parameters: dict[str, Any] | None = None

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def execute(self, _query: Any, parameters: dict[str, Any]) -> FakeResult:
        self.last_parameters = parameters
        return FakeResult(self._scalar_value)


class FakeSessionFactory:
    def __init__(self, scalar_value: Any) -> None:
        self._scalar_value = scalar_value
        self.last_session: FakeSession | None = None

    def __call__(self) -> FakeSession:
        session = FakeSession(self._scalar_value)
        self.last_session = session
        return session


def test_is_whitelisted_returns_true_for_known_user() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=1)
        repository = PostgresWhitelistRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.is_whitelisted("12345")

        assert result is True
        assert session_factory.last_session is not None
        assert session_factory.last_session.last_parameters == {"telegram_user_id": 12345}

    asyncio.run(run())


def test_is_whitelisted_returns_false_for_unknown_user() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=None)
        repository = PostgresWhitelistRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.is_whitelisted("99999")

        assert result is False

    asyncio.run(run())


def test_is_whitelisted_returns_false_for_invalid_user_id() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=1)
        repository = PostgresWhitelistRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.is_whitelisted("not-a-number")

        assert result is False
        assert session_factory.last_session is None

    asyncio.run(run())

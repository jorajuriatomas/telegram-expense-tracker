import asyncio
from typing import Any

from app.infrastructure.postgres.users_repository import PostgresUsersRepository


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


def test_find_id_returns_user_id_for_known_telegram_id() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=42)
        repository = PostgresUsersRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.find_id_by_telegram_id("12345")

        assert result == 42
        assert session_factory.last_session is not None
        assert session_factory.last_session.last_parameters == {"telegram_id": "12345"}

    asyncio.run(run())


def test_find_id_returns_none_for_unknown_telegram_id() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=None)
        repository = PostgresUsersRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.find_id_by_telegram_id("99999")

        assert result is None

    asyncio.run(run())


def test_find_id_passes_telegram_id_as_text_without_casting() -> None:
    async def run() -> None:
        # The PDF DDL stores telegram_id as text; we must not coerce it.
        session_factory = FakeSessionFactory(scalar_value=7)
        repository = PostgresUsersRepository(session_factory=session_factory)  # type: ignore[arg-type]

        await repository.find_id_by_telegram_id("not-a-number")

        assert session_factory.last_session is not None
        assert session_factory.last_session.last_parameters == {
            "telegram_id": "not-a-number",
        }

    asyncio.run(run())

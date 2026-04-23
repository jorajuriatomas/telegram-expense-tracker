import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.domain.expense import ExpenseToSave
from app.infrastructure.postgres.expense_repository import PostgresExpenseRepository


class FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    def __init__(self, scalar_value: Any) -> None:
        self._scalar_value = scalar_value
        self.executed_parameters: dict[str, Any] | None = None
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def execute(self, _query: Any, parameters: dict[str, Any]) -> FakeResult:
        self.executed_parameters = parameters
        return FakeResult(self._scalar_value)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, scalar_value: Any) -> None:
        self._scalar_value = scalar_value
        self.last_session: FakeSession | None = None

    def __call__(self) -> FakeSession:
        session = FakeSession(self._scalar_value)
        self.last_session = session
        return session


def _build_expense() -> ExpenseToSave:
    return ExpenseToSave(
        telegram_user_id=123,
        description="Pizza",
        amount=Decimal("20.00"),
        category="Food",
        source_chat_id=987,
        source_message_id=456,
        source_timestamp=datetime(2026, 4, 22, 20, 0, tzinfo=timezone.utc),
    )


def test_save_expense_returns_true_when_row_is_inserted() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=1)
        repository = PostgresExpenseRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.save_expense(_build_expense())

        assert result is True
        assert session_factory.last_session is not None
        assert session_factory.last_session.committed is True
        assert session_factory.last_session.executed_parameters is not None
        assert (
            session_factory.last_session.executed_parameters["telegram_user_id"] == 123
        )

    asyncio.run(run())


def test_save_expense_returns_false_when_row_is_not_inserted() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(scalar_value=None)
        repository = PostgresExpenseRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.save_expense(_build_expense())

        assert result is False
        assert session_factory.last_session is not None
        assert session_factory.last_session.committed is True

    asyncio.run(run())

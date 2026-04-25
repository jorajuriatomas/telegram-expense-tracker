import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.domain.expense import ExpenseToSave
from app.infrastructure.postgres.expense_repository import PostgresExpenseRepository


class FakeResult:
    """Minimal SQLAlchemy `Result` stand-in.

    Supports the two access patterns the repository uses:
      - `scalar_one_or_none()` for INSERT ... RETURNING id
      - `one_or_none()`         for DELETE ... RETURNING <columns>
    """

    def __init__(
        self,
        scalar_value: Any = None,
        row: Any = None,
    ) -> None:
        self._scalar_value = scalar_value
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._scalar_value

    def one_or_none(self) -> Any:
        return self._row


class FakeSession:
    def __init__(self, scalar_value: Any = None, row: Any = None) -> None:
        self._scalar_value = scalar_value
        self._row = row
        self.executed_parameters: dict[str, Any] | None = None
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def execute(self, _query: Any, parameters: dict[str, Any]) -> FakeResult:
        self.executed_parameters = parameters
        return FakeResult(scalar_value=self._scalar_value, row=self._row)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, scalar_value: Any = None, row: Any = None) -> None:
        self._scalar_value = scalar_value
        self._row = row
        self.last_session: FakeSession | None = None

    def __call__(self) -> FakeSession:
        session = FakeSession(scalar_value=self._scalar_value, row=self._row)
        self.last_session = session
        return session


def _build_expense() -> ExpenseToSave:
    return ExpenseToSave(
        user_id=42,
        description="Pizza",
        amount=Decimal("20.00"),
        category="Food",
        added_at=datetime(2026, 4, 22, 20, 0, tzinfo=timezone.utc),
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
        params = session_factory.last_session.executed_parameters
        assert params["user_id"] == 42
        assert params["description"] == "Pizza"
        assert params["amount"] == Decimal("20.00")
        assert params["category"] == "Food"
        # Repository normalizes tz-aware to naive UTC (DB column is `timestamp` without TZ).
        assert params["added_at"] == datetime(2026, 4, 22, 20, 0)

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


def test_delete_last_for_user_returns_record_when_row_exists() -> None:
    async def run() -> None:
        # Simulate the row Postgres returns from `DELETE ... RETURNING ...`.
        # `amount` is a string-castable Decimal because we cast `amount::numeric`.
        deleted_row = SimpleNamespace(
            description="Pizza",
            amount=Decimal("20.00"),
            category="Food",
            added_at=datetime(2026, 4, 22, 20, 0),
        )
        session_factory = FakeSessionFactory(row=deleted_row)
        repository = PostgresExpenseRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.delete_last_for_user(user_id=42)

        assert result is not None
        assert result.description == "Pizza"
        assert result.amount == Decimal("20.00")
        assert result.category == "Food"
        assert result.added_at == datetime(2026, 4, 22, 20, 0)
        assert session_factory.last_session is not None
        assert session_factory.last_session.committed is True
        assert session_factory.last_session.executed_parameters == {"user_id": 42}

    asyncio.run(run())


def test_delete_last_for_user_returns_none_when_no_rows_exist() -> None:
    async def run() -> None:
        session_factory = FakeSessionFactory(row=None)
        repository = PostgresExpenseRepository(session_factory=session_factory)  # type: ignore[arg-type]

        result = await repository.delete_last_for_user(user_id=42)

        assert result is None
        assert session_factory.last_session is not None
        # We still commit even when nothing was deleted, so the (no-op) tx ends cleanly.
        assert session_factory.last_session.committed is True

    asyncio.run(run())

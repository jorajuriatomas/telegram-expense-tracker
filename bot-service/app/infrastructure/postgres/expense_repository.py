from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.process_message import ExpenseRepository
from app.domain.expense import ExpenseRecord, ExpenseToSave


def _to_naive_utc(value: datetime) -> datetime:
    """Convert a (possibly tz-aware) datetime to naive UTC.

    The PDF DDL uses `timestamp` (no time zone). asyncpg rejects tz-aware
    datetimes for that column type, so we normalize to UTC and drop the
    tzinfo. Naive datetimes are passed through unchanged on the assumption
    that they are already UTC (the only producer is the Connector, which
    always emits ISO-8601 with a `Z`).
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class PostgresExpenseRepository(ExpenseRepository):
    """Persists and mutates expenses (`expenses` table per the PDF DDL).

    The `amount` column is `money` per the PDF spec; we cast the bound
    Decimal parameter through `numeric` to avoid locale-dependent parsing
    on the PostgreSQL side (e.g. `lc_monetary`-driven literals). On the
    way out (DELETE ... RETURNING), we cast back to numeric so Python
    receives a clean Decimal instead of a locale-formatted money string.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_expense(self, expense: ExpenseToSave) -> bool:
        query = text(
            """
            INSERT INTO expenses (
                "user_id",
                "description",
                "amount",
                "category",
                "added_at"
            )
            VALUES (
                :user_id,
                :description,
                CAST(CAST(:amount AS numeric) AS money),
                :category,
                :added_at
            )
            RETURNING "id"
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                query,
                {
                    "user_id": expense.user_id,
                    "description": expense.description,
                    "amount": expense.amount,
                    "category": expense.category,
                    "added_at": _to_naive_utc(expense.added_at),
                },
            )
            inserted = result.scalar_one_or_none() is not None
            await session.commit()
            return inserted

    async def delete_last_for_user(self, user_id: int) -> ExpenseRecord | None:
        """Delete the user's most recent expense; return what was deleted.

        Returns None if the user has no expenses. Resolves "most recent" by
        `added_at` desc, breaking ties on `id` desc (deterministic when two
        rows share a timestamp). The DELETE is keyed by primary key so we
        never delete more than one row even with concurrent writers.
        """
        query = text(
            """
            DELETE FROM expenses
            WHERE "id" = (
                SELECT "id" FROM expenses
                WHERE "user_id" = :user_id
                ORDER BY "added_at" DESC, "id" DESC
                LIMIT 1
            )
            RETURNING "description", "amount"::numeric AS amount, "category", "added_at"
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(query, {"user_id": user_id})
            row = result.one_or_none()
            await session.commit()
            if row is None:
                return None
            return ExpenseRecord(
                description=row.description,
                amount=Decimal(row.amount),
                category=row.category,
                added_at=row.added_at,
            )

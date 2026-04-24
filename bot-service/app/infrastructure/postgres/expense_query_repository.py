"""Read-side repository for expense queries.

Separate from `expense_repository` (write-side) following the CQRS-lite
pattern: queries and mutations have different concerns and can evolve
independently. This module owns the SQL for all read-only access.

Note: every query casts `amount::numeric` because the column type is
`money` (per PDF DDL) and Python receives money as a locale-formatted
string by default. Casting to numeric guarantees a Decimal back.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.expense import ExpenseRecord


class PostgresExpenseQueryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def total(
        self,
        user_id: int,
        since: datetime | None = None,
        category: str | None = None,
    ) -> Decimal:
        """Sum of expenses for a user, optionally scoped by date and category."""
        clauses = ['"user_id" = :user_id']
        params: dict[str, object] = {"user_id": user_id}

        if since is not None:
            clauses.append('"added_at" >= :since')
            params["since"] = since
        if category is not None:
            clauses.append('"category" = :category')
            params["category"] = category

        where = " AND ".join(clauses)
        query = text(
            f'SELECT COALESCE(SUM("amount"::numeric), 0) FROM expenses WHERE {where}'
        )

        async with self._session_factory() as session:
            result = await session.execute(query, params)
            return Decimal(result.scalar_one())

    async def summary_by_category(
        self,
        user_id: int,
        since: datetime | None = None,
    ) -> list[tuple[str, Decimal, int]]:
        """Returns rows of (category, total_amount, count) ordered by total desc."""
        clauses = ['"user_id" = :user_id']
        params: dict[str, object] = {"user_id": user_id}

        if since is not None:
            clauses.append('"added_at" >= :since')
            params["since"] = since

        where = " AND ".join(clauses)
        query = text(
            f"""
            SELECT "category", SUM("amount"::numeric) AS total, COUNT(*) AS count
            FROM expenses
            WHERE {where}
            GROUP BY "category"
            ORDER BY total DESC
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(query, params)
            return [
                (row.category, Decimal(row.total), int(row.count))
                for row in result.all()
            ]

    async def last_n(self, user_id: int, n: int) -> list[ExpenseRecord]:
        """Returns the N most recent expenses for a user, newest first."""
        query = text(
            """
            SELECT "description", "amount"::numeric AS amount, "category", "added_at"
            FROM expenses
            WHERE "user_id" = :user_id
            ORDER BY "added_at" DESC
            LIMIT :n
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(query, {"user_id": user_id, "n": n})
            return [
                ExpenseRecord(
                    description=row.description,
                    amount=Decimal(row.amount),
                    category=row.category,
                    added_at=row.added_at,
                )
                for row in result.all()
            ]

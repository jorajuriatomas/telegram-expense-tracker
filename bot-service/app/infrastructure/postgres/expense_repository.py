from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.process_message import ExpenseRepository
from app.domain.expense import ExpenseToSave


class PostgresExpenseRepository(ExpenseRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_expense(self, expense: ExpenseToSave) -> bool:
        query = text(
            """
            INSERT INTO expenses (
                telegram_user_id,
                description,
                amount,
                category,
                source_chat_id,
                source_message_id,
                source_timestamp
            )
            VALUES (
                :telegram_user_id,
                :description,
                :amount,
                :category,
                :source_chat_id,
                :source_message_id,
                :source_timestamp
            )
            ON CONFLICT (source_chat_id, source_message_id) DO NOTHING
            RETURNING id
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                query,
                {
                    "telegram_user_id": expense.telegram_user_id,
                    "description": expense.description,
                    "amount": expense.amount,
                    "category": expense.category,
                    "source_chat_id": expense.source_chat_id,
                    "source_message_id": expense.source_message_id,
                    "source_timestamp": expense.source_timestamp,
                },
            )
            inserted = result.scalar_one_or_none() is not None
            await session.commit()
            return inserted

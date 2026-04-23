from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.process_message import UsersRepository


class PostgresUsersRepository(UsersRepository):
    """Reads the whitelist from the `users` table (PDF DDL).

    `telegram_id` is stored as text (per spec). The PDF makes the `users`
    table the canonical whitelist source: presence in the table is the
    only authorization check we perform.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_id_by_telegram_id(self, telegram_id: str) -> int | None:
        query = text(
            """
            SELECT "id"
            FROM users
            WHERE "telegram_id" = :telegram_id
            LIMIT 1
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(query, {"telegram_id": telegram_id})
            return result.scalar_one_or_none()

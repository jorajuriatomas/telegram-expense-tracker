from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.process_message import WhitelistRepository


class PostgresWhitelistRepository(WhitelistRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def is_whitelisted(self, telegram_user_id: str) -> bool:
        try:
            telegram_user_id_int = int(telegram_user_id)
        except ValueError:
            return False

        query = text(
            """
            SELECT 1
            FROM whitelist_users
            WHERE telegram_user_id = :telegram_user_id
            LIMIT 1
            """
        )

        async with self._session_factory() as session:
            result = await session.execute(
                query,
                {"telegram_user_id": telegram_user_id_int},
            )
            return result.scalar_one_or_none() is not None

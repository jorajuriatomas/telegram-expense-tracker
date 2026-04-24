from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def _normalize_database_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver.

    Many managed Postgres providers (Railway, Heroku, Supabase, etc.) hand
    out URLs in the form `postgresql://...` (no driver suffix), which
    SQLAlchemy resolves to psycopg2 by default. We use asyncpg, so we
    rewrite the prefix here. Already-prefixed URLs are left untouched.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):  # legacy Heroku-style scheme
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        _normalize_database_url(settings.database_url),
        pool_pre_ping=True,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
    )

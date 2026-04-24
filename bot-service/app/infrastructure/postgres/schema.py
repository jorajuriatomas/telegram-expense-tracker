"""Idempotent schema initialization run at app startup.

For a small, fixed schema like this one, running `CREATE TABLE IF NOT
EXISTS` at startup is sufficient and much lighter than introducing a
full migration tool. For an evolving schema with rollbacks across
environments, Alembic would be the right choice.

This module exists primarily to support managed-Postgres providers
(Railway, Heroku, Supabase, Neon, ...) where we don't control the
postgres container and therefore can't rely on the
`/docker-entrypoint-initdb.d/` convention used by `infra/postgres/init/`.
Running it locally is harmless: every statement is idempotent.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    "id" SERIAL PRIMARY KEY,
    "telegram_id" text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    "id" SERIAL PRIMARY KEY,
    "user_id" integer NOT NULL REFERENCES users("id"),
    "description" text NOT NULL,
    "amount" money NOT NULL,
    "category" text NOT NULL,
    "added_at" timestamp NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses ("user_id");
"""


def parse_telegram_ids(raw: str) -> tuple[list[str], list[str]]:
    """Split a comma-separated list into (valid_ids, invalid_ids).

    Telegram user ids are numeric, so non-numeric entries are flagged as
    invalid. Whitespace around entries is tolerated. Empty input returns
    two empty lists.
    """
    if not raw:
        return ([], [])
    candidates = [token.strip() for token in raw.split(",")]
    candidates = [token for token in candidates if token]
    valid = [token for token in candidates if token.isdigit()]
    invalid = [token for token in candidates if not token.isdigit()]
    return (valid, invalid)


async def ensure_schema_exists(
    engine: AsyncEngine,
    initial_telegram_ids: str = "",
) -> None:
    """Create tables if missing and optionally seed the whitelist.

    The schema half is unconditional and always idempotent. The seed
    half runs only if `initial_telegram_ids` is non-empty; failures in
    the seed are logged but not raised, so a malformed env var cannot
    prevent the service from booting.
    """
    async with engine.begin() as conn:
        await conn.execute(text(_SCHEMA_SQL))
    logger.info("Schema ensured (CREATE TABLE IF NOT EXISTS executed)")

    if not initial_telegram_ids:
        logger.info("INITIAL_TELEGRAM_IDS empty; skipping whitelist seed")
        return

    valid_ids, invalid_ids = parse_telegram_ids(initial_telegram_ids)
    if invalid_ids:
        logger.warning(
            "Skipping invalid telegram_ids (not numeric): %s", invalid_ids
        )
    if not valid_ids:
        return

    try:
        async with engine.begin() as conn:
            for telegram_id in valid_ids:
                await conn.execute(
                    text(
                        'INSERT INTO users ("telegram_id") '
                        "VALUES (:telegram_id) "
                        'ON CONFLICT ("telegram_id") DO NOTHING'
                    ),
                    {"telegram_id": telegram_id},
                )
        logger.info("Whitelist seeded with %d telegram_id(s)", len(valid_ids))
    except Exception:
        # Seeding is best-effort. Service can still run with an empty whitelist.
        logger.exception("Failed to seed whitelist; continuing without it")

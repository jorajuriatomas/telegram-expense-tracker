"""Slash-command handling.

Encapsulates the logic of routing and replying to commands like
`/total`, `/summary`, `/last`, `/help`. Depends only on a query
repository (read-only); never writes.

Adding a new command is a 3-line change here plus a new query method
on the repository if needed. See `docs/CONTRIBUTING.md` for the recipe.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable, Protocol

from app.domain.categories import EXPENSE_CATEGORIES
from app.domain.expense import ExpenseRecord


class ExpenseQueryRepository(Protocol):
    async def total(
        self,
        user_id: int,
        since: datetime | None = None,
        category: str | None = None,
    ) -> Decimal:
        ...

    async def summary_by_category(
        self,
        user_id: int,
        since: datetime | None = None,
    ) -> list[tuple[str, Decimal, int]]:
        ...

    async def last_n(self, user_id: int, n: int) -> list[ExpenseRecord]:
        ...


_HANDLED_COMMANDS = ("/help", "/total", "/summary", "/last")
_HELP_TEXT = (
    "Available commands:\n"
    "/help - show this list\n"
    "/total - sum of expenses this month\n"
    "/total <category> - sum for a specific category this month\n"
    "/summary - breakdown by category this month\n"
    "/last - most recent expense"
)

# Canonical category lookup, case-insensitive.
# `_CATEGORY_BY_LOWER["food"] == "Food"`. Built once at module load.
_CATEGORY_BY_LOWER: dict[str, str] = {cat.lower(): cat for cat in EXPENSE_CATEGORIES}


def _first_of_current_month(now: datetime | None = None) -> datetime:
    """Returns the first instant of the current month in UTC, naive (matches DB column type)."""
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _format_amount(amount: Decimal) -> str:
    """`$1234.50` style. No locale - keeps output predictable."""
    return f"${amount:,.2f}"


def _resolve_category(raw: str) -> str | None:
    """Match user input against the canonical category list, case-insensitive.

    Returns the canonical capitalization (e.g. "Food") or None if there's
    no match. Categories are stored in the DB with the exact capitalization
    from EXPENSE_CATEGORIES, so user input must be normalized before query.
    """
    return _CATEGORY_BY_LOWER.get(raw.strip().lower())


class CommandHandler:
    """Dispatches `/command` messages to handlers and returns reply text.

    The handler set is fixed at construction; callers ask `is_command()`
    first and `handle()` only when true.
    """

    def __init__(self, query_repository: ExpenseQueryRepository) -> None:
        self._query_repository = query_repository
        self._handlers: dict[str, Callable[[int, str], Awaitable[str]]] = {
            "/help": self._help,
            "/total": self._total,
            "/summary": self._summary,
            "/last": self._last,
        }

    @staticmethod
    def is_command(text: str) -> bool:
        """True if the message starts with `/` and is one of the recognized commands."""
        if not text.startswith("/"):
            return False
        first_token = text.split(maxsplit=1)[0].lower()
        return first_token in _HANDLED_COMMANDS

    async def handle(self, user_id: int, text: str) -> str:
        """Dispatch to the matching handler. Assumes `is_command(text)` is True."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        handler = self._handlers[command]
        return await handler(user_id, args)

    async def _help(self, _user_id: int, _args: str) -> str:
        return _HELP_TEXT

    async def _total(self, user_id: int, args: str) -> str:
        since = _first_of_current_month()

        if args:
            category = _resolve_category(args)
            if category is None:
                valid = ", ".join(EXPENSE_CATEGORIES)
                return (
                    f"Unknown category '{args}'. "
                    f"Valid categories: {valid}"
                )
        else:
            category = None

        amount = await self._query_repository.total(
            user_id=user_id, since=since, category=category
        )
        if category:
            return f"{_format_amount(amount)} spent on {category} this month."
        return f"{_format_amount(amount)} spent this month."

    async def _summary(self, user_id: int, _args: str) -> str:
        since = _first_of_current_month()
        rows = await self._query_repository.summary_by_category(
            user_id=user_id, since=since
        )
        if not rows:
            return "No expenses recorded this month."

        total = sum((amount for _, amount, _ in rows), Decimal("0"))
        lines = [
            f"{category}: {_format_amount(amount)} ({count})"
            for category, amount, count in rows
        ]
        lines.append(f"Total: {_format_amount(total)}")
        return "Summary this month:\n" + "\n".join(lines)

    async def _last(self, user_id: int, _args: str) -> str:
        records = await self._query_repository.last_n(user_id=user_id, n=1)
        if not records:
            return "No expenses recorded yet."
        record = records[0]
        return (
            f"Last expense: {record.description} - {_format_amount(record.amount)} "
            f"[{record.category}] at {record.added_at:%Y-%m-%d %H:%M} UTC."
        )

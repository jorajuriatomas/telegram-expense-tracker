import asyncio
from datetime import datetime
from decimal import Decimal

from app.application.command_handler import CommandHandler
from app.domain.expense import ExpenseRecord


class InMemoryQueryRepository:
    """Pre-canned responses for command handler tests."""

    def __init__(
        self,
        total: Decimal = Decimal("0"),
        summary: list[tuple[str, Decimal, int]] | None = None,
        last_n_records: list[ExpenseRecord] | None = None,
    ) -> None:
        self._total = total
        self._summary = summary or []
        self._last_n_records = last_n_records or []
        self.last_total_call: dict | None = None
        self.last_summary_call: dict | None = None

    async def total(self, user_id, since=None, category=None):
        self.last_total_call = {"user_id": user_id, "since": since, "category": category}
        return self._total

    async def summary_by_category(self, user_id, since=None):
        self.last_summary_call = {"user_id": user_id, "since": since}
        return self._summary

    async def last_n(self, user_id, n):
        return self._last_n_records[:n]


class InMemoryMutationRepository:
    """Stub for the write-side dependency the handler uses for /delete."""

    def __init__(self, deleted: ExpenseRecord | None = None) -> None:
        self._deleted = deleted
        self.delete_calls: list[int] = []

    async def delete_last_for_user(self, user_id: int) -> ExpenseRecord | None:
        self.delete_calls.append(user_id)
        return self._deleted


def _build_handler(
    query: InMemoryQueryRepository | None = None,
    mutation: InMemoryMutationRepository | None = None,
) -> CommandHandler:
    return CommandHandler(
        query_repository=query or InMemoryQueryRepository(),  # type: ignore[arg-type]
        mutation_repository=mutation or InMemoryMutationRepository(),  # type: ignore[arg-type]
    )


def _run(coro):
    return asyncio.run(coro)


def test_is_command_recognizes_known_commands() -> None:
    handler = _build_handler()
    assert handler.is_command("/help")
    assert handler.is_command("/total")
    assert handler.is_command("/total food")
    assert handler.is_command("/summary")
    assert handler.is_command("/last")
    assert handler.is_command("/delete")


def test_is_command_rejects_unknown_or_non_command_text() -> None:
    handler = _build_handler()
    assert not handler.is_command("Pizza 20 bucks")
    assert not handler.is_command("/unknown")
    assert not handler.is_command("hello /total")
    assert not handler.is_command("")


def test_is_command_is_case_insensitive() -> None:
    handler = _build_handler()
    assert handler.is_command("/HELP")
    assert handler.is_command("/Total food")
    assert handler.is_command("/Delete")


def test_help_lists_available_commands() -> None:
    handler = _build_handler()
    reply = _run(handler.handle(user_id=1, text="/help"))
    assert "/help" in reply
    assert "/total" in reply
    assert "/summary" in reply
    assert "/last" in reply
    assert "/delete" in reply


def test_total_returns_formatted_amount_for_current_month() -> None:
    repo = InMemoryQueryRepository(total=Decimal("1234.50"))
    handler = _build_handler(query=repo)

    reply = _run(handler.handle(user_id=42, text="/total"))

    assert "$1,234.50" in reply
    assert "this month" in reply
    assert repo.last_total_call is not None
    assert repo.last_total_call["user_id"] == 42
    assert repo.last_total_call["category"] is None
    since = repo.last_total_call["since"]
    assert since.day == 1
    assert since.hour == 0


def test_total_with_category_argument_filters_by_that_category() -> None:
    repo = InMemoryQueryRepository(total=Decimal("320.00"))
    handler = _build_handler(query=repo)

    reply = _run(handler.handle(user_id=42, text="/total Food"))

    assert "$320.00" in reply
    assert "Food" in reply
    assert repo.last_total_call["category"] == "Food"


def test_total_normalizes_category_to_canonical_capitalization() -> None:
    """User input is matched case-insensitively and normalized before query."""
    repo = InMemoryQueryRepository(total=Decimal("320.00"))
    handler = _build_handler(query=repo)

    _run(handler.handle(user_id=42, text="/total food"))     # lowercase
    assert repo.last_total_call["category"] == "Food"

    _run(handler.handle(user_id=42, text="/total TRANSPORTATION"))  # uppercase
    assert repo.last_total_call["category"] == "Transportation"


def test_total_returns_helpful_message_for_unknown_category() -> None:
    """Reject unrecognized categories with a list of valid ones, instead of returning $0."""
    repo = InMemoryQueryRepository(total=Decimal("999.99"))
    handler = _build_handler(query=repo)

    reply = _run(handler.handle(user_id=42, text="/total comida"))

    assert "Unknown category" in reply
    assert "comida" in reply
    assert "Food" in reply  # the canonical list should be in the help
    assert repo.last_total_call is None


def test_summary_groups_by_category_and_appends_total() -> None:
    repo = InMemoryQueryRepository(
        summary=[
            ("Housing", Decimal("1200.00"), 1),
            ("Food", Decimal("320.00"), 4),
            ("Transportation", Decimal("180.00"), 2),
        ]
    )
    handler = _build_handler(query=repo)

    reply = _run(handler.handle(user_id=42, text="/summary"))

    assert "Housing: $1,200.00 (1)" in reply
    assert "Food: $320.00 (4)" in reply
    assert "Transportation: $180.00 (2)" in reply
    assert "Total: $1,700.00" in reply


def test_summary_with_no_data_returns_friendly_message() -> None:
    handler = _build_handler(query=InMemoryQueryRepository(summary=[]))
    reply = _run(handler.handle(user_id=42, text="/summary"))
    assert "No expenses" in reply


def test_last_returns_most_recent_expense() -> None:
    repo = InMemoryQueryRepository(
        last_n_records=[
            ExpenseRecord(
                description="Pizza",
                amount=Decimal("20.00"),
                category="Food",
                added_at=datetime(2026, 4, 24, 13, 30),
            )
        ]
    )
    handler = _build_handler(query=repo)

    reply = _run(handler.handle(user_id=42, text="/last"))

    assert "Pizza" in reply
    assert "$20.00" in reply
    assert "Food" in reply
    assert "2026-04-24" in reply


def test_last_with_no_data_returns_friendly_message() -> None:
    handler = _build_handler(query=InMemoryQueryRepository(last_n_records=[]))
    reply = _run(handler.handle(user_id=42, text="/last"))
    assert "No expenses" in reply


def test_delete_removes_last_expense_and_replies_with_what_was_deleted() -> None:
    deleted = ExpenseRecord(
        description="Pizza",
        amount=Decimal("20.00"),
        category="Food",
        added_at=datetime(2026, 4, 24, 13, 30),
    )
    mutation = InMemoryMutationRepository(deleted=deleted)
    handler = _build_handler(mutation=mutation)

    reply = _run(handler.handle(user_id=42, text="/delete"))

    assert "Deleted" in reply
    assert "Pizza" in reply
    assert "$20.00" in reply
    assert "Food" in reply
    assert mutation.delete_calls == [42]


def test_delete_returns_friendly_message_when_user_has_no_expenses() -> None:
    mutation = InMemoryMutationRepository(deleted=None)
    handler = _build_handler(mutation=mutation)

    reply = _run(handler.handle(user_id=42, text="/delete"))

    assert "No expenses" in reply
    assert mutation.delete_calls == [42]


def test_delete_ignores_args() -> None:
    """`/delete whatever` should still delete the last expense; args are ignored."""
    deleted = ExpenseRecord(
        description="Bus ticket",
        amount=Decimal("3.50"),
        category="Transportation",
        added_at=datetime(2026, 4, 24, 8, 0),
    )
    mutation = InMemoryMutationRepository(deleted=deleted)
    handler = _build_handler(mutation=mutation)

    reply = _run(handler.handle(user_id=42, text="/delete some unused arg"))

    assert "Bus ticket" in reply
    assert "Transportation" in reply

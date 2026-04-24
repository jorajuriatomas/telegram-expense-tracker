from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.application.command_handler import CommandHandler
from app.application.process_message import (
    ExpenseExtractor,
    ExpenseRepository,
    ProcessMessageUseCase,
    UsersRepository,
)
from app.domain.expense import ExpenseRecord, ExpenseToSave, ParsedExpense
from app.main import create_app


class InMemoryUsersRepository(UsersRepository):
    """`telegram_id -> users.id` mapping (the whitelist for tests)."""

    def __init__(self, ids_by_telegram_id: Mapping[str, int]) -> None:
        self._ids_by_telegram_id = dict(ids_by_telegram_id)

    async def find_id_by_telegram_id(self, telegram_id: str) -> int | None:
        return self._ids_by_telegram_id.get(telegram_id)


class InMemoryExpenseExtractor(ExpenseExtractor):
    def __init__(self, results_by_message: Mapping[str, ParsedExpense | None]) -> None:
        self._results_by_message = dict(results_by_message)

    async def extract(self, message_text: str) -> ParsedExpense | None:
        return self._results_by_message.get(message_text)


class FailingExpenseExtractor(ExpenseExtractor):
    async def extract(self, message_text: str) -> ParsedExpense | None:
        raise RuntimeError(f"forced extractor error for: {message_text}")


class InMemoryExpenseRepository(ExpenseRepository):
    def __init__(self, save_result: bool) -> None:
        self._save_result = save_result
        self.saved_expenses: list[ExpenseToSave] = []

    async def save_expense(self, expense: ExpenseToSave) -> bool:
        self.saved_expenses.append(expense)
        return self._save_result


class InMemoryQueryRepository:
    """Stub query repo used to test command routing through the API."""

    async def total(self, user_id, since=None, category=None):
        return Decimal("100.00")

    async def summary_by_category(self, user_id, since=None):
        return [("Food", Decimal("100.00"), 1)]

    async def last_n(self, user_id, n):
        return [
            ExpenseRecord(
                description="Pizza",
                amount=Decimal("20.00"),
                category="Food",
                added_at=datetime(2026, 4, 24, 13, 30),
            )
        ]


def create_test_client(
    ids_by_telegram_id: Mapping[str, int],
    results_by_message: Mapping[str, ParsedExpense | None] | None,
    expense_repository: ExpenseRepository,
    expense_extractor: ExpenseExtractor | None = None,
) -> TestClient:
    use_case = ProcessMessageUseCase(
        expense_extractor=expense_extractor or InMemoryExpenseExtractor(results_by_message or {}),
        users_repository=InMemoryUsersRepository(ids_by_telegram_id),
        expense_repository=expense_repository,
        command_handler=CommandHandler(query_repository=InMemoryQueryRepository()),  # type: ignore[arg-type]
    )
    app = create_app(process_message_use_case=use_case)
    return TestClient(app)


def test_process_message_returns_reply_for_basic_expense() -> None:
    repository = InMemoryExpenseRepository(save_result=True)
    client = create_test_client(
        ids_by_telegram_id={"123": 42},
        results_by_message={
            "Pizza 20 bucks": ParsedExpense(
                description="Pizza",
                amount=Decimal("20"),
                category="Food",
            )
        },
        expense_repository=repository,
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "Pizza 20 bucks",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "should_reply": True,
        "reply_text": "[Food] expense added \u2705",
    }
    assert len(repository.saved_expenses) == 1
    saved = repository.saved_expenses[0]
    assert saved.user_id == 42
    assert saved.description == "Pizza"
    assert saved.amount == Decimal("20")
    assert saved.category == "Food"


def test_process_message_ignores_non_expense_message() -> None:
    client = create_test_client(
        ids_by_telegram_id={"123": 42},
        results_by_message={"Good morning team": None},
        expense_repository=InMemoryExpenseRepository(save_result=True),
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "Good morning team",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"should_reply": False, "reply_text": None}


def test_process_message_ignores_non_whitelisted_user() -> None:
    client = create_test_client(
        ids_by_telegram_id={"999": 1},
        results_by_message={
            "Pizza 20 bucks": ParsedExpense(
                description="Pizza",
                amount=Decimal("20"),
                category="Food",
            )
        },
        expense_repository=InMemoryExpenseRepository(save_result=True),
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "Pizza 20 bucks",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"should_reply": False, "reply_text": None}


def test_process_message_returns_no_reply_when_expense_is_not_persisted() -> None:
    client = create_test_client(
        ids_by_telegram_id={"123": 42},
        results_by_message={
            "Pizza 20 bucks": ParsedExpense(
                description="Pizza",
                amount=Decimal("20"),
                category="Food",
            )
        },
        expense_repository=InMemoryExpenseRepository(save_result=False),
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "Pizza 20 bucks",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"should_reply": False, "reply_text": None}


def test_process_message_returns_500_when_unhandled_error_occurs() -> None:
    client = create_test_client(
        ids_by_telegram_id={"123": 42},
        results_by_message=None,
        expense_repository=InMemoryExpenseRepository(save_result=True),
        expense_extractor=FailingExpenseExtractor(),
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "Pizza 20 bucks",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}


def test_process_message_routes_slash_command_to_command_handler() -> None:
    """Slash commands should bypass the LLM and be answered directly."""
    repository = InMemoryExpenseRepository(save_result=True)
    client = create_test_client(
        ids_by_telegram_id={"123": 42},
        results_by_message=None,  # not used — command shouldn't hit the extractor
        expense_repository=repository,
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",
            "chat_id": "987",
            "message_text": "/total",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["should_reply"] is True
    assert "$100.00" in body["reply_text"]
    # Command must NOT have triggered an expense save.
    assert repository.saved_expenses == []


def test_process_message_silently_ignores_command_from_non_whitelisted_user() -> None:
    """Whitelist gate applies to commands too, not only to expenses."""
    client = create_test_client(
        ids_by_telegram_id={"999": 1},  # different user
        results_by_message=None,
        expense_repository=InMemoryExpenseRepository(save_result=True),
    )

    response = client.post(
        "/process-message",
        json={
            "telegram_user_id": "123",  # not in whitelist
            "chat_id": "987",
            "message_text": "/help",
            "message_id": "456",
            "timestamp": "2026-04-22T20:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"should_reply": False, "reply_text": None}

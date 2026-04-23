from collections.abc import Iterable
from decimal import Decimal

from app.application.process_message import (
    ExpenseExtractor,
    ExpenseRepository,
    ProcessMessageUseCase,
    WhitelistRepository,
)
from app.domain.expense import ExpenseToSave, ParsedExpense
from fastapi.testclient import TestClient

from app.main import create_app


class InMemoryWhitelistRepository(WhitelistRepository):
    def __init__(self, allowed_ids: Iterable[str]) -> None:
        self._allowed_ids = set(allowed_ids)

    async def is_whitelisted(self, telegram_user_id: str) -> bool:
        return telegram_user_id in self._allowed_ids


class InMemoryExpenseExtractor(ExpenseExtractor):
    def __init__(self, results_by_message: dict[str, ParsedExpense | None]) -> None:
        self._results_by_message = results_by_message

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


def create_test_client(
    allowed_ids: Iterable[str],
    results_by_message: dict[str, ParsedExpense | None] | None,
    expense_repository: ExpenseRepository,
    expense_extractor: ExpenseExtractor | None = None,
) -> TestClient:
    use_case = ProcessMessageUseCase(
        expense_extractor=expense_extractor or InMemoryExpenseExtractor(results_by_message or {}),
        whitelist_repository=InMemoryWhitelistRepository(allowed_ids),
        expense_repository=expense_repository,
    )
    app = create_app(process_message_use_case=use_case)
    return TestClient(app)


def test_process_message_returns_reply_for_basic_expense() -> None:
    client = create_test_client(
        allowed_ids={"123"},
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
    assert response.json() == {
        "should_reply": True,
        "reply_text": "[Food] expense added \u2705",
    }


def test_process_message_ignores_non_expense_message() -> None:
    client = create_test_client(
        allowed_ids={"123"},
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
    assert response.json() == {
        "should_reply": False,
        "reply_text": None,
    }


def test_process_message_ignores_non_whitelisted_user() -> None:
    client = create_test_client(
        allowed_ids={"999"},
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
    assert response.json() == {
        "should_reply": False,
        "reply_text": None,
    }


def test_process_message_returns_no_reply_when_expense_is_not_persisted() -> None:
    client = create_test_client(
        allowed_ids={"123"},
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
    assert response.json() == {
        "should_reply": False,
        "reply_text": None,
    }


def test_process_message_returns_500_when_unhandled_error_occurs() -> None:
    client = create_test_client(
        allowed_ids={"123"},
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

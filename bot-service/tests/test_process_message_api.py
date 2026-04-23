from collections.abc import Iterable

from app.application.basic_expense_parser import BasicExpenseParser
from app.application.process_message import ProcessMessageUseCase, WhitelistRepository
from fastapi.testclient import TestClient

from app.main import create_app


class InMemoryWhitelistRepository(WhitelistRepository):
    def __init__(self, allowed_ids: Iterable[str]) -> None:
        self._allowed_ids = set(allowed_ids)

    async def is_whitelisted(self, telegram_user_id: str) -> bool:
        return telegram_user_id in self._allowed_ids


def create_test_client(allowed_ids: Iterable[str]) -> TestClient:
    use_case = ProcessMessageUseCase(
        parser=BasicExpenseParser(),
        whitelist_repository=InMemoryWhitelistRepository(allowed_ids),
    )
    app = create_app(process_message_use_case=use_case)
    return TestClient(app)


def test_process_message_returns_reply_for_basic_expense() -> None:
    client = create_test_client(allowed_ids={"123"})

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
        "reply_text": "[Other] expense added \u2705",
    }


def test_process_message_ignores_non_expense_message() -> None:
    client = create_test_client(allowed_ids={"123"})

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
    client = create_test_client(allowed_ids={"999"})

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

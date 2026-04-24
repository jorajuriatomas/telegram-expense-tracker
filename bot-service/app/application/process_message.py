import logging
from typing import Protocol

from app.application.command_handler import CommandHandler
from app.domain.expense import ExpenseToSave, ParsedExpense
from app.interface.http.schemas import ProcessMessageRequest, ProcessMessageResponse

logger = logging.getLogger(__name__)


class UsersRepository(Protocol):
    """Whitelist lookup. Returns the internal `users.id` (FK target) or None."""

    async def find_id_by_telegram_id(self, telegram_id: str) -> int | None:
        ...


class ExpenseExtractor(Protocol):
    """LLM-based extractor that decides whether a message is an expense."""

    async def extract(self, message_text: str) -> ParsedExpense | None:
        ...


class ExpenseRepository(Protocol):
    """Persistence boundary for expense rows."""

    async def save_expense(self, expense: ExpenseToSave) -> bool:
        ...


class ProcessMessageUseCase:
    """Orchestrates the full pipeline.

    Two execution paths share the same whitelist gate:
      1. Slash commands (`/total`, `/summary`, ...) → CommandHandler → reply.
      2. Free text → LLM extraction → if expense, persist and reply.

    Non-whitelisted senders and non-expense free text are silently ignored
    per the PDF spec.
    """

    def __init__(
        self,
        expense_extractor: ExpenseExtractor,
        users_repository: UsersRepository,
        expense_repository: ExpenseRepository,
        command_handler: CommandHandler,
    ) -> None:
        self._expense_extractor = expense_extractor
        self._users_repository = users_repository
        self._expense_repository = expense_repository
        self._command_handler = command_handler

    async def execute(self, request: ProcessMessageRequest) -> ProcessMessageResponse:
        try:
            user_id = await self._users_repository.find_id_by_telegram_id(
                request.telegram_user_id
            )
            if user_id is None:
                # Non-whitelisted users are silently ignored per spec.
                return ProcessMessageResponse(should_reply=False, reply_text=None)

            text = request.message_text.strip()

            # Slash commands take precedence over LLM extraction.
            if self._command_handler.is_command(text):
                reply = await self._command_handler.handle(user_id, text)
                return ProcessMessageResponse(should_reply=True, reply_text=reply)

            # Free-text message: ask the LLM whether it's an expense.
            parsed_expense = await self._expense_extractor.extract(text)
            if parsed_expense is None:
                # Non-expense messages are silently ignored per spec.
                return ProcessMessageResponse(should_reply=False, reply_text=None)

            expense_to_save = ExpenseToSave(
                user_id=user_id,
                description=parsed_expense.description,
                amount=parsed_expense.amount,
                category=parsed_expense.category,
                added_at=request.timestamp,
            )
            was_saved = await self._expense_repository.save_expense(expense_to_save)
            if not was_saved:
                return ProcessMessageResponse(should_reply=False, reply_text=None)

            return ProcessMessageResponse(
                should_reply=True,
                reply_text=f"[{parsed_expense.category}] expense added \u2705",
            )
        except Exception:
            logger.exception(
                "Failed to process message",
                extra={"telegram_user_id": request.telegram_user_id},
            )
            raise

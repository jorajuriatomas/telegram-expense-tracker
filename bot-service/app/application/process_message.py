import base64
import logging
from typing import Protocol

from app.application.command_handler import CommandHandler
from app.domain.expense import ExpenseToSave, ParsedExpense
from app.interface.http.schemas import (
    ProcessImageRequest,
    ProcessMessageRequest,
    ProcessMessageResponse,
)

logger = logging.getLogger(__name__)


class UsersRepository(Protocol):
    """Whitelist lookup. Returns the internal `users.id` (FK target) or None."""

    async def find_id_by_telegram_id(self, telegram_id: str) -> int | None:
        ...


class ExpenseExtractor(Protocol):
    """LLM-based extractor for free-text messages."""

    async def extract(self, message_text: str) -> ParsedExpense | None:
        ...


class ImageExpenseExtractor(Protocol):
    """LLM-based extractor for receipt-image messages (multimodal)."""

    async def extract(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> ParsedExpense | None:
        ...


class ExpenseRepository(Protocol):
    """Persistence boundary for expense rows."""

    async def save_expense(self, expense: ExpenseToSave) -> bool:
        ...


class ProcessMessageUseCase:
    """Top-level use case for incoming Telegram messages.

    Three execution paths share the same whitelist gate and persistence path:
      1. Text + slash command -> CommandHandler -> reply.
      2. Text + free message -> text extractor -> if expense, persist + reply.
      3. Image (receipt photo) -> image extractor -> if expense, persist + reply.

    Non-whitelisted senders and "not an expense" results are silently ignored
    per the PDF spec.
    """

    def __init__(
        self,
        expense_extractor: ExpenseExtractor,
        users_repository: UsersRepository,
        expense_repository: ExpenseRepository,
        command_handler: CommandHandler,
        image_expense_extractor: ImageExpenseExtractor | None = None,
    ) -> None:
        self._expense_extractor = expense_extractor
        self._users_repository = users_repository
        self._expense_repository = expense_repository
        self._command_handler = command_handler
        self._image_expense_extractor = image_expense_extractor

    async def execute(self, request: ProcessMessageRequest) -> ProcessMessageResponse:
        """Handle a text message (free text or slash command)."""
        try:
            user_id = await self._whitelist(request.telegram_user_id)
            if user_id is None:
                return _silent_ignore()

            text = request.message_text.strip()

            # Slash commands take precedence over LLM extraction.
            if self._command_handler.is_command(text):
                reply = await self._command_handler.handle(user_id, text)
                return ProcessMessageResponse(should_reply=True, reply_text=reply)

            parsed_expense = await self._expense_extractor.extract(text)
            return await self._persist_or_ignore(
                user_id=user_id,
                parsed_expense=parsed_expense,
                added_at=request.timestamp,
            )
        except Exception:
            logger.exception(
                "Failed to process text message",
                extra={"telegram_user_id": request.telegram_user_id},
            )
            raise

    async def execute_image(self, request: ProcessImageRequest) -> ProcessMessageResponse:
        """Handle an image message (receipt photo)."""
        try:
            if self._image_expense_extractor is None:
                # Image processing wasn't wired (e.g. tests that don't need it).
                return _silent_ignore()

            user_id = await self._whitelist(request.telegram_user_id)
            if user_id is None:
                return _silent_ignore()

            try:
                image_bytes = base64.b64decode(request.image_data, validate=True)
            except (ValueError, TypeError):
                logger.warning(
                    "Rejecting image with invalid base64 payload",
                    extra={"telegram_user_id": request.telegram_user_id},
                )
                return _silent_ignore()

            parsed_expense = await self._image_expense_extractor.extract(
                image_bytes=image_bytes,
                mime_type=request.mime_type,
            )
            return await self._persist_or_ignore(
                user_id=user_id,
                parsed_expense=parsed_expense,
                added_at=request.timestamp,
            )
        except Exception:
            logger.exception(
                "Failed to process image message",
                extra={"telegram_user_id": request.telegram_user_id},
            )
            raise

    async def _whitelist(self, telegram_user_id: str) -> int | None:
        return await self._users_repository.find_id_by_telegram_id(telegram_user_id)

    async def _persist_or_ignore(
        self,
        user_id: int,
        parsed_expense: ParsedExpense | None,
        added_at,
    ) -> ProcessMessageResponse:
        """Shared tail of every successful extraction path.

        Persists the expense and returns the spec'd reply, or silently
        ignores if extraction returned None or persistence didn't insert.
        """
        if parsed_expense is None:
            return _silent_ignore()

        expense_to_save = ExpenseToSave(
            user_id=user_id,
            description=parsed_expense.description,
            amount=parsed_expense.amount,
            category=parsed_expense.category,
            added_at=added_at,
        )
        was_saved = await self._expense_repository.save_expense(expense_to_save)
        if not was_saved:
            return _silent_ignore()

        return ProcessMessageResponse(
            should_reply=True,
            reply_text=f"[{parsed_expense.category}] expense added \u2705",
        )


def _silent_ignore() -> ProcessMessageResponse:
    return ProcessMessageResponse(should_reply=False, reply_text=None)

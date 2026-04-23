import logging
from typing import Protocol

from app.domain.expense import ExpenseToSave, ParsedExpense
from app.interface.http.schemas import ProcessMessageRequest, ProcessMessageResponse

logger = logging.getLogger(__name__)


class WhitelistRepository(Protocol):
    async def is_whitelisted(self, telegram_user_id: str) -> bool:
        ...


class ExpenseExtractor(Protocol):
    async def extract(self, message_text: str) -> ParsedExpense | None:
        ...


class ExpenseRepository(Protocol):
    async def save_expense(self, expense: ExpenseToSave) -> bool:
        ...


class ProcessMessageUseCase:
    def __init__(
        self,
        expense_extractor: ExpenseExtractor,
        whitelist_repository: WhitelistRepository,
        expense_repository: ExpenseRepository,
    ) -> None:
        self._expense_extractor = expense_extractor
        self._whitelist_repository = whitelist_repository
        self._expense_repository = expense_repository

    async def execute(self, request: ProcessMessageRequest) -> ProcessMessageResponse:
        try:
            is_whitelisted = await self._whitelist_repository.is_whitelisted(
                request.telegram_user_id
            )
            if not is_whitelisted:
                return ProcessMessageResponse(should_reply=False, reply_text=None)

            parsed_expense = await self._expense_extractor.extract(request.message_text)
            if parsed_expense is None:
                return ProcessMessageResponse(should_reply=False, reply_text=None)

            expense_to_save = _build_expense_to_save(request, parsed_expense)
            if expense_to_save is None:
                return ProcessMessageResponse(should_reply=False, reply_text=None)

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


def _build_expense_to_save(
    request: ProcessMessageRequest,
    parsed_expense: ParsedExpense,
) -> ExpenseToSave | None:
    try:
        telegram_user_id = int(request.telegram_user_id)
        source_chat_id = int(request.chat_id)
        source_message_id = int(request.message_id)
    except ValueError:
        return None

    return ExpenseToSave(
        telegram_user_id=telegram_user_id,
        description=parsed_expense.description,
        amount=parsed_expense.amount,
        category=parsed_expense.category,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        source_timestamp=request.timestamp,
    )

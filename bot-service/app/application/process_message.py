from typing import Protocol

from app.application.basic_expense_parser import BasicExpenseParser
from app.interface.http.schemas import ProcessMessageRequest, ProcessMessageResponse


class WhitelistRepository(Protocol):
    async def is_whitelisted(self, telegram_user_id: str) -> bool:
        ...


class ProcessMessageUseCase:
    def __init__(
        self,
        parser: BasicExpenseParser,
        whitelist_repository: WhitelistRepository,
    ) -> None:
        self._parser = parser
        self._whitelist_repository = whitelist_repository

    async def execute(self, request: ProcessMessageRequest) -> ProcessMessageResponse:
        is_whitelisted = await self._whitelist_repository.is_whitelisted(
            request.telegram_user_id
        )
        if not is_whitelisted:
            return ProcessMessageResponse(should_reply=False, reply_text=None)

        parsed_expense = self._parser.parse(request.message_text)
        if parsed_expense is None:
            return ProcessMessageResponse(should_reply=False, reply_text=None)

        return ProcessMessageResponse(
            should_reply=True,
            reply_text=f"[{parsed_expense.category}] expense added \u2705",
        )

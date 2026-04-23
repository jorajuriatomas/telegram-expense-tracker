import logging

from fastapi import FastAPI, HTTPException

from app.application.process_message import ProcessMessageUseCase
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.llm.langchain_expense_extractor import LangChainExpenseExtractor
from app.infrastructure.postgres.connection import get_session_factory
from app.infrastructure.postgres.expense_repository import PostgresExpenseRepository
from app.infrastructure.postgres.whitelist_repository import PostgresWhitelistRepository
from app.interface.http.schemas import ProcessMessageRequest, ProcessMessageResponse

logger = logging.getLogger(__name__)


def create_app(process_message_use_case: ProcessMessageUseCase | None = None) -> FastAPI:
    app = FastAPI(title="bot-service", version="0.1.0")
    if process_message_use_case is None:
        settings = get_settings()
        configure_logging(settings.log_level)
        whitelist_repository = PostgresWhitelistRepository(
            session_factory=get_session_factory(),
        )
        expense_repository = PostgresExpenseRepository(
            session_factory=get_session_factory(),
        )
        expense_extractor = LangChainExpenseExtractor(
            llm_provider=settings.llm_provider,
            llm_model_name=settings.llm_model_name,
            llm_api_key=settings.llm_api_key,
        )
        process_message_use_case = ProcessMessageUseCase(
            expense_extractor=expense_extractor,
            whitelist_repository=whitelist_repository,
            expense_repository=expense_repository,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        settings = get_settings()
        return {
            "status": "ok",
            "service": "bot-service",
            "model": settings.llm_model_name,
        }

    @app.post("/process-message", response_model=ProcessMessageResponse)
    async def process_message(
        payload: ProcessMessageRequest,
    ) -> ProcessMessageResponse:
        try:
            return await process_message_use_case.execute(payload)
        except Exception as error:
            logger.exception(
                "Unhandled error in process-message endpoint",
                extra={"error": str(error)},
            )
            raise HTTPException(status_code=500, detail="internal_error") from error

    return app


app = create_app()

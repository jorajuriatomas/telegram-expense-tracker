"""FastAPI app factory for the Bot Service.

This module intentionally does NOT instantiate the app at import time so that
tests can import `create_app` without triggering side-effects (LLM client
initialization, settings parsing, etc.). The runtime ASGI entrypoint lives
in `app.asgi` and is referenced by uvicorn / Docker.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.application.process_message import ProcessMessageUseCase
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.llm.langchain_expense_extractor import LangChainExpenseExtractor
from app.infrastructure.postgres.connection import get_engine, get_session_factory
from app.infrastructure.postgres.expense_repository import PostgresExpenseRepository
from app.infrastructure.postgres.schema import ensure_schema_exists
from app.infrastructure.postgres.users_repository import PostgresUsersRepository
from app.interface.http.schemas import ProcessMessageRequest, ProcessMessageResponse

logger = logging.getLogger(__name__)


def create_app(process_message_use_case: ProcessMessageUseCase | None = None) -> FastAPI:
    """Build a FastAPI app.

    Pass `process_message_use_case` from tests to inject in-memory fakes.
    When omitted, the production wiring is built from env-driven settings
    and a single shared async session factory; the lifespan also runs
    `ensure_schema_exists` so the service self-bootstraps its own schema
    on managed-Postgres providers (Railway, Supabase, Heroku, ...).
    """

    is_production_wiring = process_message_use_case is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if is_production_wiring:
            settings = get_settings()
            try:
                await ensure_schema_exists(
                    get_engine(),
                    initial_telegram_ids=settings.initial_telegram_ids,
                )
            except Exception:
                # Surface the failure clearly but let the app boot anyway —
                # it'll fail fast on the first DB call with a useful traceback.
                logger.exception("Failed to ensure schema at startup")
        yield

    app = FastAPI(title="bot-service", version="0.1.0", lifespan=lifespan)

    if is_production_wiring:
        settings = get_settings()
        configure_logging(settings.log_level)
        session_factory = get_session_factory()
        users_repository = PostgresUsersRepository(session_factory=session_factory)
        expense_repository = PostgresExpenseRepository(session_factory=session_factory)
        expense_extractor = LangChainExpenseExtractor(
            llm_provider=settings.llm_provider,
            llm_model_name=settings.llm_model_name,
            llm_api_key=settings.llm_api_key,
        )
        process_message_use_case = ProcessMessageUseCase(
            expense_extractor=expense_extractor,
            users_repository=users_repository,
            expense_repository=expense_repository,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        # Liveness only. Internals (model name, db url) intentionally not exposed.
        return {"status": "ok", "service": "bot-service"}

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

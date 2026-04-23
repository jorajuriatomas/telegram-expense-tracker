from fastapi import FastAPI

from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="bot-service", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "bot-service",
            "model": settings.llm_model_name,
        }

    return app


app = create_app()

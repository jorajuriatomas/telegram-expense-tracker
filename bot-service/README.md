# Bot Service

Python 3.11 FastAPI service that processes incoming expense messages: verifies the sender is whitelisted, asks the LLM (via LangChain) to extract structured data, and persists into PostgreSQL.

This service is intentionally agnostic of Telegram. It accepts a normalized HTTP payload from the [connector service](../connector-service/README.md) and is the only component aware of the database.

## Architecture

Layered following clean architecture; dependencies point inward.

```
app/
├── domain/               # Pure types (ParsedExpense, ExpenseToSave) and category constants
├── application/          # Use case (ProcessMessageUseCase) + repository protocols
├── infrastructure/       # Concrete adapters
│   ├── llm/              # LangChain extractor (provider-agnostic)
│   └── postgres/         # asyncpg repositories (users, expenses)
├── interface/http/       # Pydantic request/response schemas
├── core/                 # Settings + logging
├── main.py               # FastAPI factory (no side effects on import)
└── asgi.py               # Runtime ASGI app: app = create_app()
```

The use case knows nothing about Postgres, FastAPI or LangChain — it only depends on protocols (`UsersRepository`, `ExpenseRepository`, `ExpenseExtractor`) defined alongside it. Concrete adapters are wired in `main.create_app()` (production) or by the tests (in-memory fakes).

## HTTP API

### `POST /process-message`

Request:

```json
{
  "telegram_user_id": "1218557035",
  "chat_id": "1218557035",
  "message_text": "Pizza 20 bucks",
  "message_id": "42",
  "timestamp": "2026-04-23T16:30:00Z"
}
```

Successful response (whitelisted user, valid expense, persisted):

```json
{ "should_reply": true, "reply_text": "[Food] expense added \u2705" }
```

Silent-ignore response (non-whitelisted user, OR not an expense, OR persistence failed):

```json
{ "should_reply": false, "reply_text": null }
```

The connector uses `should_reply` to decide whether to call Telegram's `sendMessage`. Silent ignores are the spec'd behavior for non-authorized senders and non-expense messages.

### `GET /health`

```json
{ "status": "ok", "service": "bot-service" }
```

Liveness only. Internals (model name, DB URL) are intentionally not exposed.

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `BOT_SERVICE_HOST` | yes | `0.0.0.0` in Docker, `127.0.0.1` for local |
| `BOT_SERVICE_PORT` | yes | Default `8000` |
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@host:5432/db` |
| `LLM_PROVIDER` | yes | `groq`, `google_genai`, `openai`, `anthropic`, `mistralai`, ... |
| `LLM_MODEL_NAME` | yes | Provider-specific model id |
| `LLM_API_KEY` | yes | Internally translated to the provider's well-known env var (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, ...) |
| `LOG_LEVEL` | no | Default `INFO` |

A reference [`.env.example`](.env.example) is included.

## Local development (without Docker)

```bash
cd bot-service
python -m venv .venv
source .venv/bin/activate            # Linux / macOS
# .venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt

cp .env.example .env
# Edit .env. DATABASE_URL must point to a reachable Postgres with the schema applied.

uvicorn app.asgi:app --host 0.0.0.0 --port 8000 --reload
```

The schema lives in [`../infra/postgres/init/001_schema.sql`](../infra/postgres/init/001_schema.sql) and matches the PDF DDL exactly.

## Tests

In-memory fakes for repositories and the LLM chain — no external dependencies needed.

```bash
pip install pytest httpx
pytest -q
```

Coverage:

| File | Scope |
|---|---|
| `tests/test_users_repository.py` | Whitelist lookup query and parameter binding |
| `tests/test_expense_repository.py` | INSERT contract and row-inserted detection |
| `tests/test_langchain_expense_extractor.py` | LLM output parsing, validation, fallback to `Other` |
| `tests/test_process_message_api.py` | Full FastAPI request → response cycle through the use case |

15 tests total, ~1 second.

## Concurrency model

- FastAPI + uvicorn runs the asyncio event loop. All endpoints are `async def`.
- `asyncpg` provides a connection pool managed by SQLAlchemy's `async_sessionmaker`.
- Each `/process-message` call holds a short-lived session per repository call.
- The LLM call is awaited; the loop processes other requests while it is pending.

For higher throughput, set `--workers N` on uvicorn to fan out across processes. The single-process default is sufficient for a chatbot use case.

## Adding a new LLM provider

1. Add the provider's LangChain integration to `requirements.txt` (e.g. `langchain-mistralai==...`).
2. Add `"<provider_id>": "<EXPECTED_API_KEY_ENV_VAR>"` to `_PROVIDER_API_KEY_ENV_VARS` in `app/infrastructure/llm/langchain_expense_extractor.py`.
3. Set `LLM_PROVIDER`, `LLM_MODEL_NAME`, `LLM_API_KEY` accordingly in `.env`.

No code changes elsewhere.

## Related

- [Connector service](../connector-service/README.md)
- [Database schema](../infra/postgres/init/001_schema.sql)

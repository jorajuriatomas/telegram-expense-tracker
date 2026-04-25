# Bot Service

Python 3.11 FastAPI service that processes incoming Telegram messages: verifies the sender is whitelisted, routes to the right handler (slash command or LLM-based expense extraction), and persists or queries expenses against PostgreSQL.

This service is intentionally agnostic of Telegram. It accepts a normalized HTTP payload from the [connector service](../connector-service/README.md) and is the only component aware of the database.

## Architecture

Layered following clean architecture; dependencies point inward.

```
app/
├── domain/                          # Pure types: ParsedExpense, ExpenseToSave, ExpenseRecord
├── application/                     # Use cases + protocols
│   ├── process_message.py           # Top-level use case (whitelist + routing)
│   └── command_handler.py           # Slash-command dispatch + reply formatting
├── infrastructure/                  # Concrete adapters
│   ├── llm/                         # LangChain extractor (provider-agnostic)
│   └── postgres/                    # asyncpg repositories
│       ├── users_repository.py      # Whitelist lookup
│       ├── expense_repository.py    # Write side: INSERT
│       ├── expense_query_repository.py  # Read side: SUM, GROUP BY, ORDER BY (CQRS-lite)
│       └── schema.py                # Idempotent schema bootstrap at startup
├── interface/http/                  # Pydantic request/response schemas
├── core/                            # Settings + logging
├── main.py                          # FastAPI factory (no side effects on import)
└── asgi.py                          # Runtime ASGI app: app = create_app()
```

The use case knows nothing about Postgres, FastAPI or LangChain — it only depends on protocols (`UsersRepository`, `ExpenseRepository`, `ExpenseExtractor`, `ExpenseQueryRepository`) defined alongside the code that uses them. Concrete adapters are wired in `main.create_app()` (production) or by the tests (in-memory fakes).

## Message routing

Inside `ProcessMessageUseCase.execute()`, every incoming message goes through the same gate and then branches:

```
incoming message
    │
    ├── whitelist check (users table)
    │       └── not in users → silent ignore (per spec)
    │
    ├── starts with "/" ?
    │       ├── YES → CommandHandler → reply with query result
    │       └── NO  → LLM extraction
    │                   ├── not an expense → silent ignore (per spec)
    │                   └── is an expense → INSERT + reply "[Category] expense added ✅"
```

Whitelist gate applies uniformly to commands and free-text messages.

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

Response cases:

| Scenario | Response |
|---|---|
| Whitelisted user, valid expense, persisted | `{"should_reply": true, "reply_text": "[Food] expense added ✅"}` |
| Whitelisted user, slash command | `{"should_reply": true, "reply_text": "<formatted query result>"}` |
| Non-whitelisted user (any text) | `{"should_reply": false, "reply_text": null}` |
| Free text that the LLM does NOT consider an expense | `{"should_reply": false, "reply_text": null}` |
| Persistence failure | `{"should_reply": false, "reply_text": null}` |
| Unhandled error | HTTP 500 `{"detail": "internal_error"}` |

The connector uses `should_reply` to decide whether to call Telegram's `sendMessage`. Silent ignores are the spec'd behavior for non-authorized senders and non-expense messages.

### `GET /health`

```json
{ "status": "ok", "service": "bot-service" }
```

Liveness only. Internals (model name, DB URL) are intentionally not exposed.

## Slash commands

Free-text messages are routed to the LLM. Messages starting with `/` are routed to `CommandHandler` and answered without invoking the LLM.

| Command | Behavior |
|---|---|
| `/help` | Lists available commands |
| `/total` | Sum of expenses for the current calendar month |
| `/total <category>` | Sum filtered by category (e.g. `/total Food`) |
| `/summary` | Per-category breakdown for the current month, plus total |
| `/last` | Description, amount, category and timestamp of the most recent expense |
| `/delete` | Removes the most recent expense and replies with what was deleted |

Commands are case-insensitive (`/HELP` works). Unknown commands fall through to LLM extraction (which will likely treat them as non-expense and silently ignore).

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `BOT_SERVICE_HOST` | yes | `0.0.0.0` in Docker, `127.0.0.1` for local |
| `BOT_SERVICE_PORT` | yes | Default `8000` |
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@host:5432/db` (auto-normalized from `postgresql://`) |
| `LLM_PROVIDER` | yes | `groq`, `google_genai`, `openai`, `anthropic`, `mistralai`, ... |
| `LLM_MODEL_NAME` | yes | Provider-specific model id |
| `LLM_API_KEY` | yes | Internally translated to the provider's well-known env var (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, ...) |
| `LOG_LEVEL` | no | Default `INFO` |
| `INITIAL_TELEGRAM_IDS` | no | Comma-separated whitelist seeded at startup (idempotent) |

A reference [`.env.example`](.env.example) is included.

## Local development (without Docker)

```bash
cd bot-service
python -m venv .venv
source .venv/bin/activate            # Linux / macOS
# .venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt

cp .env.example .env
# Edit .env. DATABASE_URL must point to a reachable Postgres.
# Schema is bootstrapped automatically at startup; no manual SQL needed.

uvicorn app.asgi:app --host 0.0.0.0 --port 8000 --reload
```

The schema bootstrap module is at [`app/infrastructure/postgres/schema.py`](app/infrastructure/postgres/schema.py) and runs idempotently on every startup. The same DDL also lives in [`../infra/postgres/init/001_schema.sql`](../infra/postgres/init/001_schema.sql) for the `docker-entrypoint-initdb.d` mechanism in local Docker.

## Tests

In-memory fakes for repositories, the LLM chain, and the query repository — no external dependencies needed.

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
| `tests/test_schema.py` | `parse_telegram_ids` parsing logic |
| `tests/test_command_handler.py` | Command dispatch, formatting, and edge cases (15 tests) |
| `tests/test_process_message_api.py` | Full FastAPI request → response cycle including command routing |

~50 tests total, ~3 seconds.

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

## Adding a new slash command

1. Add the command string to `_HANDLED_COMMANDS` in `app/application/command_handler.py`.
2. Add an entry to the `self._handlers` dict in `CommandHandler.__init__`.
3. Implement the handler method (`async def _mycommand(self, user_id, args) -> str`).
4. If the command needs new data, add a method to the appropriate Protocol in `command_handler.py`: `ExpenseQueryRepository` for reads, `ExpenseMutationRepository` for writes. Implement on the matching infrastructure class (`expense_query_repository.py` or `expense_repository.py`).
5. Add tests in `tests/test_command_handler.py`.
6. Update `_HELP_TEXT` so `/help` lists the new command.

## Related

- [Connector service](../connector-service/README.md)
- [Database schema](../infra/postgres/init/001_schema.sql)

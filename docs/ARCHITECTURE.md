# Architecture

This document is the canonical reference for how the system is organized, why it's organized that way, and how data flows through it. It supersedes the earlier `architecture-step1.md`, which captured intermediate planning during Step 1 of the build.

The audience is anyone who needs to navigate the codebase to understand, modify, or extend it.

---

## 1. System overview

```
 ┌──────────┐   webhook    ┌────────────────┐   POST /process-message   ┌─────────────┐    SQL    ┌──────────┐
 │ Telegram │ ───────────▶ │   Connector    │ ─────────────────────────▶│     Bot     │ ─────────▶│ Postgres │
 │   API    │ ◀─────────── │  (Node, ESM)   │ ◀─────────────────────────│  (Python)   │ ◀─────────│  (DDL)   │
 └──────────┘   reply      └────────────────┘   { should_reply, ... }   └──────┬──────┘           └──────────┘
                                                                               │
                                                                               ▼
                                                                          ┌─────────┐
                                                                          │   LLM   │
                                                                          │ (any    │
                                                                          │ Lang-   │
                                                                          │ Chain   │
                                                                          │ provider│
                                                                          └─────────┘
```

Two services backed by one PostgreSQL instance. They share no code, no models, no transitive deps. They communicate exclusively over HTTP, with a JSON contract that lives in `connector-service/src/contracts/botService.ts` and is mirrored by Pydantic schemas in `bot-service/app/interface/http/schemas.py`.

---

## 2. Service responsibilities

### Connector Service

Stack: Node.js 20 + TypeScript + Express, ESM only.

Owns:

- The Telegram webhook endpoint.
- Verification of the secret token Telegram echoes back.
- Filtering Telegram updates: only text messages are forwarded; photos, edits, channel posts, etc. are dropped silently.
- Normalization of the Telegram payload into the bot service contract.
- Outbound calls to the Telegram Bot API (`sendMessage`).

Does NOT own:

- Business rules (whitelist, expense detection, categorization).
- Database access.
- LLM access.
- Any persistent state.

### Bot Service

Stack: Python 3.11 + FastAPI + SQLAlchemy async + asyncpg + LangChain.

Owns:

- All business rules: whitelist authorization, expense detection, category classification.
- LLM-based extraction of structured data from natural language messages.
- Persistence into PostgreSQL.
- The HTTP contract with the connector.

Does NOT own:

- Telegram-specific concerns. The bot accepts a normalized payload and emits a normalized response. It would work identically behind a Slack, WhatsApp, or CLI front-end.

### PostgreSQL

Owns:

- The single source of truth for the whitelist (`users`) and persisted expenses (`expenses`).
- Schema is created on first container start via files in `infra/postgres/init/`, in alphabetical order.

---

## 3. Data flow — sequence diagrams

### 3.1 Happy path: whitelisted user, valid expense

```
User                     Telegram          Connector              Bot Service           LangChain   PostgreSQL
 │                          │                  │                       │                    │            │
 │ "Pizza 20 bucks"         │                  │                       │                    │            │
 ├─────────────────────────▶│                  │                       │                    │            │
 │                          │ POST webhook     │                       │                    │            │
 │                          │ + secret header  │                       │                    │            │
 │                          ├─────────────────▶│ verify secret         │                    │            │
 │                          │◀─────────────────┤ 200 OK (immediately)  │                    │            │
 │                          │                  │ (process in bg)       │                    │            │
 │                          │                  ├──────────────────────▶│ POST /process-msg  │            │
 │                          │                  │                       │ find_id_by_tg_id   │            │
 │                          │                  │                       ├───────────────────────────────▶ │
 │                          │                  │                       │◀─────────────────────────────── │ id=42
 │                          │                  │                       ├───────────────────▶│ extract()  │
 │                          │                  │                       │                    │ chat call  │
 │                          │                  │                       │◀───────────────────┤ Parsed     │
 │                          │                  │                       │ INSERT             │            │
 │                          │                  │                       ├───────────────────────────────▶ │
 │                          │                  │                       │◀─────────────────────────────── │ id
 │                          │                  │◀──────────────────────┤ {should_reply:true,│            │
 │                          │                  │                       │  reply_text:"..."} │            │
 │                          │ POST sendMessage │                       │                    │            │
 │                          │◀─────────────────┤                       │                    │            │
 │ "[Food] expense added ✅"│                  │                       │                    │            │
 │◀─────────────────────────┤                  │                       │                    │            │
```

### 3.2 Non-whitelisted user

```
... up to the bot's whitelist lookup ...
 │ find_id_by_telegram_id ──▶  PostgreSQL
 │ ◀── None
 │ Use case returns {should_reply: false, reply_text: null}
 │ Bot responds 200 with that body
 │ Connector receives should_reply=false, does nothing
 │ User sees no reply (silent ignore — required by PDF)
```

### 3.3 Non-expense message

```
... up to the LLM call ...
 │ LangChain.extract("Hola que tal")
 │ ◀── ParsedExpense with is_expense=false → returns None
 │ Use case returns {should_reply: false, reply_text: null}
 │ User sees no reply (silent ignore — required by PDF)
```

### 3.4 Bot service error (e.g. LLM unavailable)

```
... up to the LLM call ...
 │ LangChain.extract(...) raises ResourceExhausted
 │ Use case re-raises (logged via logger.exception)
 │ Endpoint catches → returns 500 {"detail":"internal_error"}
 │ Connector logs the failure (background — does not retry)
 │ Telegram already received 200 from the webhook ACK; no retry from their side either
 │ User sees no reply
```

The decision to ACK the webhook before processing is the reason a slow or failing LLM does not turn into duplicate persistence. See section 7.

---

## 4. Module organization

### 4.1 Bot service

```
bot-service/
├── app/
│   ├── domain/
│   │   ├── categories.py            # The 11 valid categories as a tuple constant
│   │   └── expense.py               # ParsedExpense (LLM output), ExpenseToSave (write), ExpenseRecord (read)
│   ├── application/
│   │   ├── process_message.py       # Top-level use case: whitelist gate + routing
│   │   └── command_handler.py       # Slash-command dispatch (/help, /total, /summary, /last, /delete)
│   ├── infrastructure/
│   │   ├── llm/
│   │   │   └── langchain_expense_extractor.py    # LangChain-based ExpenseExtractor (provider-agnostic)
│   │   └── postgres/
│   │       ├── connection.py        # Cached engine + session factory
│   │       ├── schema.py            # Idempotent schema bootstrap at startup
│   │       ├── users_repository.py  # Whitelist lookup (find_id_by_telegram_id)
│   │       ├── expense_repository.py        # Write side: INSERT with money cast and tz coercion
│   │       └── expense_query_repository.py  # Read side: SUM, GROUP BY, ORDER BY (CQRS-lite)
│   ├── interface/
│   │   └── http/
│   │       └── schemas.py           # Pydantic request/response models
│   ├── core/
│   │   ├── config.py                # Pydantic Settings, env-driven, fail-fast
│   │   └── logging.py               # Log configuration
│   ├── main.py                      # create_app() factory — NO side effects on import
│   └── asgi.py                      # app = create_app() — runtime entry for uvicorn
├── tests/                           # Hermetic suite (in-memory fakes, no external deps)
├── requirements.txt
├── pyproject.toml
└── Dockerfile                       # Slim Python 3.11 image
```

The dependency direction is `infrastructure → application → domain`. The use case knows nothing about Postgres, FastAPI, or LangChain — it depends only on Protocols defined alongside it.

The persistence layer follows a CQRS-lite split: `expense_repository` (writes) and `expense_query_repository` (reads) are separate so each side can evolve its SQL without affecting the other. They share the same connection pool.

### 4.2 Connector service

```
connector-service/
├── src/
│   ├── contracts/                       # Cross-process types — single source of truth
│   │   ├── botService.ts                # Mirrors bot's Pydantic schemas
│   │   └── telegram.ts                  # Subset of Telegram Update we consume
│   ├── application/
│   │   └── processTelegramUpdate.ts     # Use case: filter, normalize, forward, relay
│   ├── infrastructure/
│   │   ├── bot/botServiceClient.ts      # HTTP client → bot service
│   │   └── telegram/telegramClient.ts   # HTTP client → Telegram Bot API
│   ├── interface/
│   │   └── http/
│   │       └── telegramWebhookHandler.ts # Express handler: secret check + async ACK
│   ├── config/
│   │   └── env.ts                       # Strict env-var loader, fail-fast at startup
│   ├── logger.ts                        # Minimal structured logger
│   ├── app.ts                           # Express app factory
│   └── server.ts                        # Composition root: wires everything and listens
├── tests/                               # Hermetic suite using node:test + tsx
├── package.json
├── tsconfig.json
└── Dockerfile                           # Multi-stage build (build → runtime)
```

### 4.3 Infrastructure

```
infra/postgres/init/
├── 001_schema.sql                       # users + expenses tables (PDF DDL preserved at the letter)
└── 002_seed.sh                          # INITIAL_TELEGRAM_IDS-driven whitelist seed
                                         # .sh because Postgres' init mechanism only exposes env
                                         # vars to shell scripts, not to .sql files
```

Top-level orchestration:

```
docker-compose.yml                       # Three services: postgres, bot-service, connector-service
                                         # depends_on with service_healthy gating
.env.example                             # Single source of runtime configuration
.env                                     # Local-only, NEVER committed
```

---

## 5. The HTTP contract between services

The contract has one endpoint: `POST /process-message`.

Request shape (defined in `connector-service/src/contracts/botService.ts` and mirrored by `bot-service/app/interface/http/schemas.py`):

```json
{
  "telegram_user_id": "123456789",
  "chat_id": "123456789",
  "message_text": "Pizza 20 bucks",
  "message_id": "42",
  "timestamp": "2026-04-23T16:30:00Z"
}
```

All fields are required. `telegram_user_id` and `chat_id` are stored as strings to preserve the PDF's modeling of `users.telegram_id` as `text`. `timestamp` is ISO-8601 with `Z`; the bot service's repository normalizes to naive UTC before inserting.

Response shape:

```json
{ "should_reply": true,  "reply_text": "[Food] expense added \u2705" }
```

OR (for any silent-ignore case):

```json
{ "should_reply": false, "reply_text": null }
```

The connector uses `should_reply` to decide whether to call Telegram's `sendMessage`. Silent ignores are the spec'd behavior for non-authorized senders and non-expense messages.

---

## 6. Database schema

The schema lives in `infra/postgres/init/001_schema.sql` and is preserved at the letter from the PDF DDL:

```sql
CREATE TABLE users (
  "id" SERIAL PRIMARY KEY,
  "telegram_id" text UNIQUE NOT NULL
);

CREATE TABLE expenses (
  "id" SERIAL PRIMARY KEY,
  "user_id" integer NOT NULL REFERENCES users("id"),
  "description" text NOT NULL,
  "amount" money NOT NULL,
  "category" text NOT NULL,
  "added_at" timestamp NOT NULL
);
```

Notes on the type choices, all of which are deliberate:

- **`telegram_id` is `text`**, not integer, even though Telegram IDs are numeric. The PDF says `text` and we preserve it. The repository does no coercions.
- **`users` is the whitelist.** Presence in the table is the only authorization check. Non-whitelisted senders are silently ignored.
- **`amount` is `money`.** Controversial type (locale-dependent `lc_monetary` parsing of literals) but PDF-accurate. The repository inserts with `CAST(:amount::numeric::money)` to bypass the locale issue.
- **`added_at` is `timestamp`** (no time zone). The connector emits ISO-8601 with `Z`; the repository normalizes to UTC and drops the tzinfo before binding, because asyncpg rejects tz-aware values for `timestamp` columns.
- **`expenses.user_id` is FK to `users.id`** — every expense is tied to a user via the internal id, not via the telegram_id directly.

A supporting index exists on `expenses(user_id)` for the most common access pattern (per-user history).

---

## 7. LLM abstraction

The bot service does not import any specific LLM provider's SDK. Instead it uses LangChain's `init_chat_model`:

```python
chat_model = init_chat_model(
    model=settings.llm_model_name,
    model_provider=settings.llm_provider,
    temperature=0,
)
```

`model_provider` is a string like `"openai"`, `"google_genai"`, `"groq"`, `"anthropic"`, etc. LangChain dispatches to the correct provider package and returns an instance of the appropriate ChatModel.

Each provider expects its API key in a different environment variable (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, etc.). To avoid leaking that detail to the user-facing config, the extractor maintains a small mapping table and translates the generic `LLM_API_KEY` into the provider-specific env var at startup:

```python
_PROVIDER_API_KEY_ENV_VARS = {
    "openai":       "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "anthropic":    "ANTHROPIC_API_KEY",
    "groq":         "GROQ_API_KEY",
    ...
}
```

Structured output is enforced by `chat_model.with_structured_output(_ExpenseExtractionOutput)`, which makes the LLM return a Pydantic-validated JSON object with the exact fields we need (`is_expense`, `description`, `amount`, `category`). Internally, LangChain uses the provider's tool-calling / function-calling primitives so the response is guaranteed-shaped.

To add a new provider, see `docs/CONTRIBUTING.md` recipe "Add a new LLM provider".

---

## 8. Concurrency model

The bot service is async end-to-end:

- FastAPI runs on the asyncio event loop (uvicorn).
- All endpoint handlers are `async def`.
- Postgres is accessed via SQLAlchemy async (`AsyncSession`) over asyncpg, with a connection pool managed by `async_sessionmaker`.
- The LLM call is awaited via LangChain's `ainvoke`.
- A single shared `session_factory` is constructed once in `main.create_app()` and passed to both repositories.

While one request is awaiting the LLM (typically 1–2 seconds), the event loop continues serving other requests. This satisfies the PDF's "must handle concurrent requests" requirement without needing multiple workers.

For higher throughput in production, set `--workers N` on uvicorn to fan out across processes.

The connector service is also async (Node's default), but the relevant detail is the **webhook ACK pattern**: the handler calls `res.status(200).json(...)` immediately after secret verification, then fires the processing as a background task with `void promise.then().catch()`. This decouples Telegram's webhook timeout from downstream latency. Without this, a slow LLM call would cause Telegram to retry the webhook and the bot service would persist duplicate expenses.

---

## 9. Error handling and silent ignore policy

The system distinguishes two classes of "no reply":

**Silent ignores** — expected behavior, returns `200 {should_reply: false, reply_text: null}`:

- Sender is not in the `users` whitelist.
- Message is not an expense (LLM returned `is_expense=false`).
- Persistence reported no row inserted (e.g. constraint conflict handled by `ON CONFLICT`).

**Errors** — unexpected failures, return `500 {"detail": "internal_error"}`:

- LLM call fails (network, quota, deprecated model, etc.).
- Database write fails (connection lost, FK violation, type error, etc.).
- Pydantic validation rejects the request payload (returns 422 actually, FastAPI default).

The silent ignores are **required by the PDF**: non-authorized users and non-expense messages must not produce a reply. The 500s are propagated up to the connector, which logs them but does NOT retry — Telegram already received its 200 from the webhook ACK, so no further retry can happen.

If you find yourself wanting to retry on the bot side, think twice. Retries belong outside the request path (e.g. in a queue worker), not inline.

---

## 10. Configuration model

All runtime configuration is sourced from environment variables. There is exactly one source of truth: the top-level `.env` file, distributed by `docker-compose.yml` to each service's container.

There is **no service-level `.env`** read at runtime in production (the per-service `.env.example` files exist for local dev outside Docker). There are NO hardcoded URLs, ports, model names, secrets, or paths anywhere in the code.

Both services validate their configuration at startup and refuse to boot if anything is missing or malformed:

- Bot service: `app.core.config.Settings` (Pydantic Settings) with explicit `Field(alias=...)` per env var.
- Connector service: `src/config/env.ts` with a `requireEnv()` helper that throws on missing values, plus URL and path-prefix validation.

This satisfies the PDF's "Setting up a new bot should not require any code changes. Avoid hard-coded values."

---

## 11. Testing strategy

Both suites are **hermetic**: no real Telegram, no real LLM, no real Postgres. Tests run in ~1 second each and don't require any external setup.

The technique is the same on both sides: define interfaces (Python `Protocol`, TypeScript shape types), implement them with in-memory fakes for the tests, and let the production wiring use the real adapters.

Bot service test coverage:

- `tests/test_users_repository.py` — query construction and parameter binding.
- `tests/test_expense_repository.py` — INSERT contract and inserted-row detection.
- `tests/test_langchain_expense_extractor.py` — output parsing, validation, fallback to "Other" for invalid categories.
- `tests/test_process_message_api.py` — full FastAPI request → response cycle through the use case, covering: happy path, non-whitelisted, non-expense, persistence-failed, unhandled-error.

Connector service test coverage:

- `tests/health.test.ts` — `/health` endpoint contract.
- `tests/processTelegramUpdate.test.ts` — use case: text-message filter, normalization, forwarding, reply relay.
- `tests/telegramWebhookHandler.test.ts` — secret verification, async ACK, background-error isolation.

22 tests total. CI-ready.

For how to write new tests, see `docs/CONTRIBUTING.md`.

---

## 12. Operational concerns

**Bring-up order.** `docker-compose.yml` declares `depends_on` with `condition: service_healthy`. Postgres has a `pg_isready` healthcheck; the bot service has a `/health` healthcheck. The connector waits for the bot to be healthy before starting. So a single `docker compose up` results in the right boot sequence without race conditions.

**First-init seeding (local Docker).** Postgres' init scripts (`/docker-entrypoint-initdb.d/`) run only the first time the volume is initialized. `docker compose down` preserves the volume; `docker compose down -v` blows it away and triggers re-seeding.

**Auto-schema at startup (managed Postgres).** Managed providers (Railway, Heroku, Supabase, etc.) don't expose the `docker-entrypoint-initdb.d` mechanism. To bootstrap the schema in those environments without operational intervention, the bot service runs `app.infrastructure.postgres.schema.ensure_schema_exists` in its FastAPI lifespan: every statement is `CREATE TABLE IF NOT EXISTS` / `ON CONFLICT DO NOTHING`, so it's safe to run on every boot. The `INITIAL_TELEGRAM_IDS` env var (same name as the local seed script consumes) is honored here too. For an evolving schema across many environments, the right tool would be Alembic — kept out of scope for a single fixed schema.

**Rebuild discipline.** The Dockerfiles `COPY` source code at build time — there is no live mount. A `restart` does not pick up code changes; a code change requires `docker compose up --build`.

**Logs.** Both services log to stdout. View live with `docker compose logs -f`.

**Webhook for local dev.** Telegram requires an HTTPS public URL. Locally we use `ngrok http 3000` to tunnel. In production, the connector would be deployed behind a real HTTPS endpoint and ngrok would not be needed.

---

## 13. Security model

What the system protects against and what it explicitly does not.

**Protected against:**

- **Unauthorized webhook callers.** The connector verifies the `X-Telegram-Bot-Api-Secret-Token` header against `TELEGRAM_WEBHOOK_SECRET`. Requests without a matching secret are rejected with 401. This is Telegram's official mechanism for proving "I'm Telegram, not an attacker pretending to be Telegram".
- **Unauthorized expense entry.** Even if an attacker bypasses the secret check, they still need to be in the `users` whitelist to have any effect. Non-whitelisted senders are silently dropped at the use case layer.
- **SQL injection via expense data.** All queries use parameterized binds via SQLAlchemy/asyncpg; user-controlled strings never go into raw SQL.
- **SQL injection via env-driven seed.** The `INITIAL_TELEGRAM_IDS` parser validates that each token is numeric (`^[0-9]+$`) before binding. Malformed values are skipped with a warning.
- **Credential leakage in `/health`.** The health endpoint exposes only `status` and `service`. Model name, DB URL, and API keys are intentionally NOT included in the response.

**NOT protected against (out of scope for this challenge):**

- **Service-to-service authentication between connector and bot.** They sit on the same trusted network (Docker bridge or Railway's private network). Adding mTLS or shared-secret HMAC between them is a production hardening step.
- **Rate limiting per Telegram user.** A whitelisted user could spam expenses and exhaust the LLM quota. Mitigation belongs in a middleware layer (e.g. Redis-backed token bucket).
- **DDoS at the webhook.** Behind the trusted network there's no rate limiting. Production-grade deploys would put a WAF / rate limiter (Cloudflare, Railway/Vercel built-in) in front of the connector.
- **Secret rotation automation.** Secrets live in `.env` and Railway variables; rotation is manual. A real production deploy would integrate with a secret manager (AWS Secrets Manager, Doppler, Infisical).
- **Audit logging.** All inserts go to `expenses` but there's no separate audit trail of who did what when (for forensics/compliance).

## 14. Performance considerations

The system is designed for the typical chat-bot load profile (low to moderate request rate, latency dominated by the LLM call). Key choices:

- **End-to-end async.** No request-thread blocking on I/O (DB or LLM). Single-process uvicorn handles concurrent requests via asyncio.
- **Connection pooling.** asyncpg's pool (managed by SQLAlchemy `async_sessionmaker`) avoids per-request connection setup overhead.
- **Webhook ACK before processing.** Removes the LLM latency from Telegram's perspective entirely — the perceived latency for the user is just `Telegram → bot reply` round-trip.
- **No N+1 patterns.** Each `/process-message` call performs at most three DB operations: one SELECT (whitelist), one INSERT (expense), and an implicit COMMIT.

Anti-patterns explicitly avoided:

- No synchronous I/O in async handlers.
- No global state (each request is self-contained).
- No request-time schema introspection (schema is created once at startup).

For higher throughput beyond what one process can handle, set `--workers N` on uvicorn to fan out across processes. Postgres pool sizing should scale accordingly.

## 15. 
# Expense Telegram Bot

Telegram chatbot that lets a whitelisted user log expenses by sending short natural-language messages (`Pizza 20 bucks`). Built as two independent services backed by PostgreSQL.

Built for the Darwin AI Engineering Seniority Test.

## Overview

The system is split into two services that communicate over HTTP:

- **Connector Service** (Node.js 20, ESM, TypeScript, Express) — owns the Telegram boundary. Receives the webhook, normalizes the payload, forwards to the bot service, and relays the reply back to Telegram.
- **Bot Service** (Python 3.11, FastAPI, async) — owns the business rules. Verifies the sender is on the whitelist, asks the LLM (via LangChain) whether the message is an expense, extracts `description / amount / category`, and persists into PostgreSQL.

A single PostgreSQL instance backs both services with the exact schema specified in the PDF DDL.

```
 ┌──────────┐  webhook   ┌────────────────┐   POST /process-message   ┌─────────────┐   SQL    ┌──────────┐
 │ Telegram │ ─────────▶ │   Connector    │ ─────────────────────────▶│     Bot     │ ────────▶│ Postgres │
 │   API    │ ◀───────── │  (Node, ESM)   │ ◀─────────────────────────│  (Python)   │ ◀────────│  (DDL)   │
 └──────────┘   reply    └────────────────┘   { should_reply, ... }   └──────┬──────┘          └──────────┘
                                                                            │
                                                                            ▼
                                                                       ┌─────────┐
                                                                       │   LLM   │
                                                                       │ (Groq / │
                                                                       │ Gemini /│
                                                                       │ OpenAI) │
                                                                       └─────────┘
```

## Quick start

Prerequisites:

- **Docker Desktop** running.
- An **LLM API key** — Groq's free tier is the recommended default (no card, no billing). See [LLM provider](#llm-provider).
- A **Telegram bot token** from `@BotFather`.
- **`ngrok`** (or any HTTPS tunnel) to expose the connector to Telegram during local testing.

```bash
cp .env.example .env
# Open .env and fill in:
#   LLM_API_KEY                 your Groq / Gemini / OpenAI key
#   TELEGRAM_BOT_TOKEN          token from @BotFather
#   TELEGRAM_WEBHOOK_SECRET     any random alphanumeric string
#   INITIAL_TELEGRAM_IDS        your Telegram numeric id (or a comma-separated list)

docker compose up --build
```

Wait for the three services to become healthy. In another terminal, expose the connector publicly and register the webhook with Telegram:

```bash
ngrok http 3000
# copy the https://...ngrok-free.app URL it shows

curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"<NGROK_URL>/telegram/webhook","secret_token":"<SECRET>","allowed_updates":["message"]}'
```

Open Telegram, send `Pizza 20 bucks` to the bot. You should receive `[Food] expense added ✅`.

## Configuration

All runtime configuration is sourced from a single root `.env`. No secrets, URLs, model names, ports or paths are hardcoded anywhere in the code.

| Variable | Purpose | Example |
|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_PORT` | Postgres credentials | `expenses` / `postgres` / `postgres` / `5432` |
| `INITIAL_TELEGRAM_IDS` | Comma-separated whitelist seeded on first DB init | `1218557035,9876543210` |
| `BOT_SERVICE_PORT` | Bot service HTTP port | `8000` |
| `LLM_PROVIDER` | LangChain provider id | `groq` / `google_genai` / `openai` / `anthropic` |
| `LLM_MODEL_NAME` | Model id for the chosen provider | `llama-3.3-70b-versatile` |
| `LLM_API_KEY` | API key for the chosen provider | `gsk_...` |
| `LOG_LEVEL` | Bot service log level | `INFO` |
| `CONNECTOR_PORT` | Connector HTTP port | `3000` |
| `TELEGRAM_BOT_TOKEN` | Token from `@BotFather` | `123:ABC...` |
| `TELEGRAM_WEBHOOK_SECRET` | Shared secret Telegram echoes back in `X-Telegram-Bot-Api-Secret-Token` | `webhook-secret-...` |
| `TELEGRAM_WEBHOOK_PATH` | Path the connector exposes for Telegram | `/telegram/webhook` |
| `TELEGRAM_API_BASE_URL` | Telegram Bot API base URL | `https://api.telegram.org` |
| `BOT_SERVICE_PROCESS_MESSAGE_PATH` | Bot service endpoint path | `/process-message` |

### LLM provider

The bot service uses LangChain's `init_chat_model`, so swapping providers requires only changing three env values — no code changes.

| Provider | `LLM_PROVIDER` | Example model | Notes |
|---|---|---|---|
| Groq | `groq` | `llama-3.3-70b-versatile` | Free tier, very low latency. Default. |
| Gemini | `google_genai` | `gemini-2.5-flash` | Free tier (project must be eligible). |
| OpenAI | `openai` | `gpt-4o-mini` | Paid. |
| Anthropic | `anthropic` | `claude-3-5-haiku-latest` | Paid. |

The mapping `provider → required env var` lives in `bot-service/app/infrastructure/llm/langchain_expense_extractor.py`.

## Repository layout

```
.
├── bot-service/             # Python 3.11 FastAPI service (LangChain + asyncpg)
├── connector-service/       # Node 20 Express service (ESM, TypeScript)
├── infra/postgres/          # SQL schema + env-driven seed
├── docker-compose.yml       # Orchestrates the full stack
├── .env.example             # Single source of runtime config
└── docs/                    # Architecture notes
```

Each service has its own README:

- [`bot-service/README.md`](bot-service/README.md)
- [`connector-service/README.md`](connector-service/README.md)

## Tests

Both suites are hermetic — in-memory fakes for repositories and the LLM chain, no external dependencies needed.

```bash
# Bot service (15 tests, ~1s)
cd bot-service
pip install -r requirements.txt pytest httpx
pytest -q

# Connector service (7 tests, ~1s)
cd connector-service
npm install
npm test
```

## Design decisions

A short list of choices made deliberately, with the reasoning.

- **Schema fidelity to the PDF DDL.** `users` and `expenses` are created exactly as specified, including the `money` column type. The repository casts `:amount::numeric::money` at insert time to avoid locale-dependent literal parsing on the server.
- **Whitelist is the `users` table.** The PDF makes it the canonical authorization source. Presence in `users` is the only authentication step; non-whitelisted senders are silently ignored per spec.
- **Provider-agnostic LLM.** `init_chat_model` plus a small `provider → env-var` mapping keeps the extractor decoupled from any specific vendor. Swapping providers is an `.env` change, not a code change.
- **Cross-service contracts in `connector-service/src/contracts/`.** The HTTP request/response shapes between connector and bot live in a single module imported by both the use case and the HTTP client, mirroring the Pydantic schemas on the bot side. Eliminates type drift across the boundary.
- **Webhook ACK before processing.** The connector returns `200 OK` to Telegram immediately and processes the update in the background. A slow LLM call no longer triggers Telegram's retry → no duplicate processing.
- **Side-effect-free imports.** `bot-service/app/main.py` only exposes `create_app`. The runtime ASGI app lives in `app/asgi.py` so tests can import the factory without booting the LLM client.
- **Env-driven whitelist seed.** `infra/postgres/init/002_seed.sh` reads `INITIAL_TELEGRAM_IDS` (comma-separated) from the container env. Implemented as a shell script because Postgres' init mechanism only exposes env vars to `.sh` files, not to `.sql`.
- **`tz`-aware → naive UTC at the repository boundary.** Per the PDF, `expenses.added_at` is `timestamp` (no time zone). The connector emits ISO-8601 with `Z`, so the repository normalizes to UTC and drops `tzinfo` before binding.

## Non-goals / known limitations

Honest list of what the system does *not* do, by design or scope.

- **One expense per message.** The extractor's Pydantic schema returns a single expense. Multi-expense messages would only persist the first one parsed. Aligns with the PDF example (`"Pizza 20 bucks"`); easily extended by changing the schema to a list and looping in the use case.
- **No content-based deduplication.** Three identical messages create three expense rows — each `send` is treated as a separate user intent.
- **Edits / deletions in Telegram do not propagate.** Only `message` updates are processed (`edited_message`, `channel_post`, etc. are ignored).
- **No admin endpoint.** Whitelist management is via SQL or `INITIAL_TELEGRAM_IDS` only. A REST admin layer is out of scope for this challenge.

## Reference

- Architecture deep-dive: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Recipes for common changes: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)

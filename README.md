# Expense Telegram Bot

Telegram chatbot that lets a whitelisted user log expenses by sending short natural-language messages (`Pizza 20 bucks`). Built as two independent services backed by PostgreSQL.

Built for the Darwin AI Engineering Seniority Test.

---

## Table of contents

- [Overview](#overview)
- [Live demo](#live-demo)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Repository layout](#repository-layout)
- [Tests](#tests)
- [Documentation](#documentation)
- [Author](#author)

---

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
                                                                       │ (Gemini │
                                                                       │  / Groq │
                                                                       │ / OpenAI)│
                                                                       └─────────┘
```

Example interaction:

```
User → "Pizza 20 bucks"
Bot  → "[Food] expense added ✅"

User → "Hola que tal"
Bot  → (silence — non-expense message, ignored per spec)

User → "Uber 35"
Bot  → "[Transportation] expense added ✅"
```

The bot also supports slash commands for querying past expenses:

```
User → "/help"
Bot  → "Available commands: /help, /total, /summary, /last ..."

User → "/total"
Bot  → "$55.00 spent this month."

User → "/summary"
Bot  → "Summary this month:
        Transportation: $35.00 (1)
        Food: $20.00 (1)
        Total: $55.00"

User → "/last"
Bot  → "Last expense: Uber — $35.00 [Transportation] at 2026-04-24 13:30 UTC."
```

---

## Live demo

A live instance is deployed on Railway and reachable through Telegram.

- **Bot username:** [`@tomas_jorajuria_bot`](https://t.me/tomas_jorajuria_bot)
- **Connector health:** https://reasonable-alignment-production.up.railway.app/health
- **Bot service health:** https://exemplary-healing-production-5afb.up.railway.app/health

To test live: search `@tomas_jorajuria_bot` on Telegram and send `Pizza 20 bucks`. The bot replies with `[Food] expense added ✅`.

> Note: only telegram_ids registered in the `users` table receive replies (per spec). To request access, share your Telegram numeric id (you can get it from [@userinfobot](https://t.me/userinfobot)) and it can be added with a one-line SQL insert — see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Quick start

Prerequisites:

- **Docker Desktop** running.
- An **LLM API key** — Gemini's free tier is the recommended default (no card, no billing). See the [LLM provider](#llm-provider) section.
- A **Telegram bot token** from `@BotFather`.
- **`ngrok`** (or any HTTPS tunnel) to expose the connector to Telegram during local testing.

```bash
cp .env.example .env
# Open .env and fill in:
#   LLM_API_KEY                 your Gemini / Groq / OpenAI key
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

For deployment to a real environment (Railway, Heroku, etc.), see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Configuration

All runtime configuration is sourced from a single root `.env`. No secrets, URLs, model names, ports or paths are hardcoded anywhere in the code.

| Variable | Purpose | Example |
|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_PORT` | Postgres credentials | `expenses` / `postgres` / `postgres` / `5432` |
| `INITIAL_TELEGRAM_IDS` | Comma-separated whitelist seeded on first DB init | `<your-telegram-id>` or `<id1>,<id2>` |
| `BOT_SERVICE_PORT` | Bot service HTTP port | `8000` |
| `LLM_PROVIDER` | LangChain provider id | `google_genai` / `groq` / `openai` / `anthropic` |
| `LLM_MODEL_NAME` | Model id for the chosen provider | `gemini-2.5-flash` |
| `LLM_API_KEY` | API key for the chosen provider | `AIza...` |
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
| Gemini | `google_genai` | `gemini-2.5-flash` | Free tier (project must be eligible) |
| Groq | `groq` | `llama-3.3-70b-versatile` | Free tier, very low latency |
| OpenAI | `openai` | `gpt-4o-mini` | Paid |
| Anthropic | `anthropic` | `claude-3-5-haiku-latest` | Paid |

The mapping `provider → required env var` lives in `bot-service/app/infrastructure/llm/langchain_expense_extractor.py`. To add a new provider, see [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

---

## Repository layout

```
.
├── bot-service/             # Python 3.11 FastAPI service (LangChain + asyncpg)
├── connector-service/       # Node 20 Express service (ESM, TypeScript)
├── infra/postgres/          # SQL schema + env-driven seed
├── docker-compose.yml       # Orchestrates the full stack
├── .env.example             # Single source of runtime config
└── docs/                    # Architecture, deployment, decisions
```

Each service has its own README:

- [`bot-service/README.md`](bot-service/README.md)
- [`connector-service/README.md`](connector-service/README.md)

---

## Tests

Both suites are hermetic — in-memory fakes for repositories and the LLM chain, no external dependencies needed.

```bash
# Bot service (~21 tests, ~1s)
cd bot-service
pip install -r requirements.txt pytest httpx
pytest -q

# Connector service (~7 tests, ~1s)
cd connector-service
npm install
npm test
```

CI-ready out of the box.

---

## Documentation

The repo has several complementary docs, each with a different audience:

| Doc | When to read it |
|---|---|
| [`README.md`](README.md) | First time visiting — what the project is and how to run it |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Need to navigate the codebase or make non-trivial changes |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | Need a recipe for a common change (add provider, add field, etc.) |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deploying to a real environment (Railway, Heroku, etc.) |
| [`bot-service/README.md`](bot-service/README.md) | Working on the Python side |
| [`connector-service/README.md`](connector-service/README.md) | Working on the Node side |
| Inline docstrings | Writing or modifying a specific module |

---


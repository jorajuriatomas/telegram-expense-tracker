# Step 1 - Architecture and Folder Structure

## Goal

Build a Telegram expense bot using two independent services:

- Connector Service (Node.js LTS, ESM)
- Bot Service (Python 3.11+)

PostgreSQL is the shared database.

## High-Level Architecture

1. Telegram user sends message to Telegram Bot.
2. Connector Service receives the update from Telegram webhook.
3. Connector validates incoming payload shape and forwards normalized message to Bot Service over HTTP.
4. Bot Service validates whitelist, detects whether it is an expense, extracts structured data, categorizes, and stores in PostgreSQL.
5. Bot Service returns a response payload to Connector.
6. Connector sends final text response back to Telegram chat.

## Service Boundaries

### Connector Service (Node.js)

Responsibilities:

- Telegram webhook endpoint
- Telegram API communication
- Input normalization for Bot Service
- Response relay to Telegram

Non-responsibilities:

- Expense parsing logic
- Whitelist/business rules
- Database writes

### Bot Service (Python)

Responsibilities:

- Business rules (whitelist, expense detection)
- LangChain-based extraction and categorization
- Persistence to PostgreSQL
- Return final response text to Connector

Non-responsibilities:

- Direct Telegram API operations

## Communication Contract (Draft)

Connector -> Bot (HTTP POST /process-message)

- telegram_user_id: string
- chat_id: string
- message_text: string
- message_id: string
- timestamp: string (ISO-8601)

Bot -> Connector (HTTP 200)

- should_reply: boolean
- reply_text: string | null

Behavior:

- If user is not whitelisted: should_reply=false
- If message is not an expense: should_reply=false
- If saved successfully: should_reply=true and reply_text="[Category] expense added ✅"

## Concurrency Strategy (Bot Service)

- Use async API server to handle concurrent requests.
- Keep DB access and LLM invocation isolated behind service interfaces.
- Use short-lived request scope + pooled DB connections.

## Configuration Strategy

- Environment variables only.
- No hardcoded secrets, URLs, ports, tokens, or model names.

## Folder Structure (from scratch)

Darwin IA/

- connector-service/
  - src/
  - tests/
- bot-service/
  - app/
  - tests/
- infra/
  - postgres/
- docs/
  - architecture-step1.md

## Clean Architecture Mapping (planned)

Connector Service layers:

- Interface: webhook controller
- Application: message forwarding use case
- Infrastructure: Telegram client, Bot Service HTTP client

Bot Service layers:

- Interface: HTTP API controller
- Application: process message use case
- Domain: expense entity and business rules
- Infrastructure: PostgreSQL repositories, LangChain adapter

## Reasonable Defaults Chosen

- Connector transport to Bot: HTTP JSON
- Bot API style: REST endpoint for message processing
- Shared DB ownership: Bot Service manages business tables
- Ignore policy: non-whitelisted and non-expense messages produce no reply

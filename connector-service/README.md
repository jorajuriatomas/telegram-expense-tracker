# Connector Service

Node.js 20 / Express service (ESM, TypeScript) that owns the Telegram boundary. Receives Telegram webhooks, normalizes the payload, forwards to the bot service, and relays the reply back to Telegram.

This service is intentionally thin: no business rules, no database, no LLM. All decisions about whether and what to reply live in the [bot service](../bot-service/README.md).

## Architecture

```
src/
├── contracts/                       # Cross-process types — single source of truth
│   ├── botService.ts                # ProcessMessageRequest / Response (mirrors bot's Pydantic)
│   └── telegram.ts                  # TelegramUpdate / TelegramTextMessage subset
├── application/
│   └── processTelegramUpdate.ts     # Use case: filter, normalize, forward, relay
├── infrastructure/
│   ├── bot/botServiceClient.ts      # HTTP client → bot service
│   └── telegram/telegramClient.ts   # HTTP client → Telegram Bot API
├── interface/http/
│   └── telegramWebhookHandler.ts    # Express handler: secret check + async ACK
├── config/env.ts                    # Strict env-var loader (fail-fast on missing/malformed)
├── logger.ts                        # Minimal structured logger
├── app.ts                           # Express app factory
└── server.ts                        # Composition root
```

Cross-process types (the request/response between services and the Telegram update shape) live in `contracts/` and are imported by both the use case and the HTTP client. This is what prevents the wire format from drifting between caller and transport.

## Webhook flow

1. Telegram POSTs an update to `<TELEGRAM_WEBHOOK_PATH>` with a `X-Telegram-Bot-Api-Secret-Token` header.
2. The handler verifies the header against `TELEGRAM_WEBHOOK_SECRET`. Mismatch → `401`.
3. The handler **immediately responds `200 OK`** to Telegram and processes the update in the background. This decouples Telegram's webhook timeout from the downstream LLM/DB latency, so a slow bot service does not trigger Telegram's retry → no duplicate processing.
4. In the background: if the update contains a text message, the use case normalizes it into the `ProcessMessageRequest` contract and POSTs it to the bot service.
5. If the bot's reply has `should_reply=true`, the connector calls `sendMessage` on the Telegram API with the reply text.

Non-text updates (photos, stickers, edits, channel posts, etc.) are silently dropped before reaching the bot service.

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `PORT` | yes | HTTP port (e.g. `3000`) |
| `NODE_ENV` | no | `production` / `development` |
| `TELEGRAM_BOT_TOKEN` | yes | From `@BotFather` |
| `TELEGRAM_WEBHOOK_SECRET` | yes | 1–256 chars `[A-Za-z0-9_-]`, registered with `setWebhook` |
| `TELEGRAM_WEBHOOK_PATH` | yes | Must start with `/`, e.g. `/telegram/webhook` |
| `TELEGRAM_API_BASE_URL` | yes | `https://api.telegram.org` |
| `BOT_SERVICE_BASE_URL` | yes | e.g. `http://bot-service:8000` (Docker) or `http://localhost:8000` (local) |
| `BOT_SERVICE_PROCESS_MESSAGE_PATH` | yes | Must start with `/`, e.g. `/process-message` |

A reference [`.env.example`](.env.example) is included. The loader (`src/config/env.ts`) validates types at startup and fails fast on missing or malformed values — the service refuses to boot misconfigured.

## Local development (without Docker)

```bash
cd connector-service
npm install
cp .env.example .env
# Edit .env. BOT_SERVICE_BASE_URL must point to a reachable bot service.

npm run dev
```

`npm run dev` runs `tsx watch src/server.ts` with auto-reload on changes.

## Tests

Uses Node's built-in `node:test` runner with `tsx` for TypeScript transpilation. No external dependencies invoked.

```bash
npm test
```

Coverage:

| File | Scope |
|---|---|
| `tests/health.test.ts` | `/health` endpoint contract |
| `tests/processTelegramUpdate.test.ts` | Use case: text-message filter, normalization, forwarding, reply relay |
| `tests/telegramWebhookHandler.test.ts` | Secret verification, async ACK, background-error isolation |

7 tests total, ~1 second.

To verify TypeScript types compile cleanly without emitting:

```bash
npx tsc -p tsconfig.json --noEmit
```

## Build

```bash
npm run build    # tsc → emits dist/
npm start        # node dist/src/server.js
```

The Dockerfile uses a multi-stage build: compile in a build stage, then copy `dist/` into a slim runtime image with only production deps.

## Related

- [Bot service](../bot-service/README.md)

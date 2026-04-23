import type { RequestHandler } from "express";
import type { TelegramUpdate } from "../../contracts/telegram.js";
import { logError, logInfo } from "../../logger.js";

const TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token";

/**
 * Express handler for Telegram's webhook endpoint.
 *
 * - Verifies the shared secret header that Telegram echoes back.
 * - ACKs the webhook with `200 OK` immediately and processes the update
 *   asynchronously. This prevents Telegram from retrying the webhook
 *   when the downstream Bot Service is slow (Telegram retries failed
 *   or slow webhooks, which would cause duplicate processing).
 */
export function createTelegramWebhookHandler({
  processTelegramUpdate,
  webhookSecret,
}: {
  processTelegramUpdate: (update: TelegramUpdate) => Promise<unknown>;
  webhookSecret: string;
}): RequestHandler {
  return function telegramWebhookHandler(req, res) {
    const incomingSecret = req.get(TELEGRAM_SECRET_HEADER);
    if (incomingSecret !== webhookSecret) {
      logError("Rejected Telegram webhook due to invalid secret");
      res.status(401).json({ error: "unauthorized" });
      return;
    }

    res.status(200).json({ status: "ok" });

    // Fire-and-forget: errors are logged but never bubble to the response.
    void processTelegramUpdate(req.body as TelegramUpdate)
      .then((result) => {
        logInfo("Telegram update processed", { status: result });
      })
      .catch((error: unknown) => {
        logError("Failed to process Telegram update", {
          error: error instanceof Error ? error.message : String(error),
        });
      });
  };
}

import type { RequestHandler } from "express";
import type { TelegramUpdate } from "../../application/processTelegramUpdate.js";
import { logError, logInfo } from "../../logger.js";

const TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token";

export function createTelegramWebhookHandler({
  processTelegramUpdate,
  webhookSecret,
}: {
  processTelegramUpdate: (update: TelegramUpdate) => Promise<unknown>;
  webhookSecret: string;
}): RequestHandler {
  return async function telegramWebhookHandler(req, res) {
    const incomingSecret = req.get(TELEGRAM_SECRET_HEADER);
    if (incomingSecret !== webhookSecret) {
      logError("Rejected Telegram webhook due to invalid secret");
      return res.status(401).json({ error: "unauthorized" });
    }

    try {
      const result = await processTelegramUpdate(req.body as TelegramUpdate);
      logInfo("Telegram update processed", { status: result });
      return res.status(200).json({ status: "ok" });
    } catch (error) {
      logError("Failed to process Telegram update", {
        error: error instanceof Error ? error.message : String(error),
      });
      return res.status(500).json({ error: "internal_error" });
    }
  };
}

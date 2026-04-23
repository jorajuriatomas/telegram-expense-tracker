const TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token";

export function createTelegramWebhookHandler({ processTelegramUpdate, webhookSecret }) {
  return async function telegramWebhookHandler(req, res) {
    const incomingSecret = req.get(TELEGRAM_SECRET_HEADER);
    if (incomingSecret !== webhookSecret) {
      return res.status(401).json({ error: "unauthorized" });
    }

    try {
      await processTelegramUpdate(req.body);
      return res.status(200).json({ status: "ok" });
    } catch (error) {
      console.error("Failed to process Telegram update", error);
      return res.status(500).json({ error: "internal_error" });
    }
  };
}

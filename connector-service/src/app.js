import express from "express";

export function createApp({ telegramWebhookPath, telegramWebhookHandler }) {
  const app = express();

  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.status(200).json({ status: "ok", service: "connector-service" });
  });

  app.post(telegramWebhookPath, telegramWebhookHandler);

  return app;
}

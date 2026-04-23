import express from "express";
import type { RequestHandler } from "express";

type CreateAppOptions = {
  telegramWebhookPath: string;
  telegramWebhookHandler: RequestHandler;
};

export function createApp({ telegramWebhookPath, telegramWebhookHandler }: CreateAppOptions) {
  const app = express();

  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.status(200).json({ status: "ok", service: "connector-service" });
  });

  app.post(telegramWebhookPath, telegramWebhookHandler);

  return app;
}

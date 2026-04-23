import { createApp } from "./app.js";
import { createProcessTelegramUpdate } from "./application/processTelegramUpdate.js";
import { env } from "./config/env.js";
import { BotServiceClient } from "./infrastructure/bot/botServiceClient.js";
import { TelegramClient } from "./infrastructure/telegram/telegramClient.js";
import { createTelegramWebhookHandler } from "./interface/http/telegramWebhookHandler.js";

const botServiceClient = new BotServiceClient({
  baseUrl: env.botServiceBaseUrl,
  processMessagePath: env.botServiceProcessMessagePath,
});

const telegramClient = new TelegramClient({
  apiBaseUrl: env.telegramApiBaseUrl,
  botToken: env.telegramBotToken,
});

const processTelegramUpdate = createProcessTelegramUpdate({
  botServiceClient,
  telegramClient,
});

const telegramWebhookHandler = createTelegramWebhookHandler({
  processTelegramUpdate,
  webhookSecret: env.telegramWebhookSecret,
});

const app = createApp({
  telegramWebhookPath: env.telegramWebhookPath,
  telegramWebhookHandler,
});

app.listen(env.port, () => {
  console.log(`connector-service listening on port ${env.port}`);
});

import dotenv from "dotenv";

dotenv.config();

function requireEnv(name) {
  const value = process.env[name];
  if (!value || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const env = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: Number.parseInt(requireEnv("PORT"), 10),
  telegramBotToken: requireEnv("TELEGRAM_BOT_TOKEN"),
  telegramWebhookSecret: requireEnv("TELEGRAM_WEBHOOK_SECRET"),
  botServiceBaseUrl: requireEnv("BOT_SERVICE_BASE_URL"),
};

if (Number.isNaN(env.port) || env.port <= 0) {
  throw new Error("Environment variable PORT must be a valid positive integer");
}

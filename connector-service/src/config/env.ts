import dotenv from "dotenv";

dotenv.config();

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

type Env = {
  nodeEnv: string;
  port: number;
  telegramBotToken: string;
  telegramWebhookSecret: string;
  telegramWebhookPath: string;
  telegramApiBaseUrl: string;
  botServiceBaseUrl: string;
  botServiceProcessMessagePath: string;
};

export const env: Env = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: Number.parseInt(requireEnv("PORT"), 10),
  telegramBotToken: requireEnv("TELEGRAM_BOT_TOKEN"),
  telegramWebhookSecret: requireEnv("TELEGRAM_WEBHOOK_SECRET"),
  telegramWebhookPath: requireEnv("TELEGRAM_WEBHOOK_PATH"),
  telegramApiBaseUrl: requireEnv("TELEGRAM_API_BASE_URL"),
  botServiceBaseUrl: requireEnv("BOT_SERVICE_BASE_URL"),
  botServiceProcessMessagePath: requireEnv("BOT_SERVICE_PROCESS_MESSAGE_PATH"),
};

if (Number.isNaN(env.port) || env.port <= 0) {
  throw new Error("Environment variable PORT must be a valid positive integer");
}

if (!env.telegramWebhookPath.startsWith("/")) {
  throw new Error("Environment variable TELEGRAM_WEBHOOK_PATH must start with '/'");
}

if (!env.botServiceProcessMessagePath.startsWith("/")) {
  throw new Error(
    "Environment variable BOT_SERVICE_PROCESS_MESSAGE_PATH must start with '/'",
  );
}

function validateUrl(name: string, value: string): void {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) {
      throw new Error();
    }
  } catch {
    throw new Error(`Environment variable ${name} must be a valid http/https URL`);
  }
}

validateUrl("TELEGRAM_API_BASE_URL", env.telegramApiBaseUrl);
validateUrl("BOT_SERVICE_BASE_URL", env.botServiceBaseUrl);

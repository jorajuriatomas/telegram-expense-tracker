import type {
  ProcessMessageRequest,
  ProcessMessageResponse,
} from "../contracts/botService.js";
import type {
  TelegramTextMessage,
  TelegramUpdate,
} from "../contracts/telegram.js";

type ProcessTelegramUpdateOptions = {
  botServiceClient: {
    processMessage: (payload: ProcessMessageRequest) => Promise<ProcessMessageResponse>;
  };
  telegramClient: {
    sendMessage: (payload: {
      chatId: string;
      text: string;
      replyToMessageId: string;
    }) => Promise<unknown>;
  };
};

export type ProcessTelegramUpdateResult = "ignored" | "replied" | "processed_no_reply";

function isTextMessage(
  update: TelegramUpdate,
): update is TelegramUpdate & { message: TelegramTextMessage } {
  return (
    typeof update?.message?.text === "string" &&
    update.message.text.trim() !== "" &&
    update.message.from?.id !== undefined &&
    update.message.chat?.id !== undefined &&
    update.message.message_id !== undefined
  );
}

function toIsoTimestamp(unixTimestamp: number | undefined): string {
  if (typeof unixTimestamp === "number") {
    return new Date(unixTimestamp * 1000).toISOString();
  }
  return new Date().toISOString();
}

function normalizeMessage(message: TelegramTextMessage): ProcessMessageRequest {
  return {
    telegram_user_id: String(message.from.id),
    chat_id: String(message.chat.id),
    message_text: message.text,
    message_id: String(message.message_id),
    timestamp: toIsoTimestamp(message.date),
  };
}

export function createProcessTelegramUpdate({
  botServiceClient,
  telegramClient,
}: ProcessTelegramUpdateOptions) {
  return async function processTelegramUpdate(
    update: TelegramUpdate,
  ): Promise<ProcessTelegramUpdateResult> {
    if (!isTextMessage(update)) {
      return "ignored";
    }

    const normalizedMessage = normalizeMessage(update.message);
    const botResponse = await botServiceClient.processMessage(normalizedMessage);

    if (botResponse?.should_reply === true && typeof botResponse.reply_text === "string") {
      await telegramClient.sendMessage({
        chatId: normalizedMessage.chat_id,
        text: botResponse.reply_text,
        replyToMessageId: normalizedMessage.message_id,
      });
      return "replied";
    }

    return "processed_no_reply";
  };
}

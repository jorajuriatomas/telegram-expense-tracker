export type TelegramUpdate = {
  message?: {
    message_id?: number;
    date?: number;
    text?: string;
    from?: { id?: number | string };
    chat?: { id?: number | string };
    [key: string]: unknown;
  };
};

type TextMessage = {
  message_id: number;
  date?: number;
  text: string;
  from: { id: number | string };
  chat: { id: number | string };
};

type NormalizedMessage = {
  telegram_user_id: string;
  chat_id: string;
  message_text: string;
  message_id: string;
  timestamp: string;
};

type BotServiceResponse = {
  should_reply?: boolean;
  reply_text?: string | null;
};

type ProcessTelegramUpdateOptions = {
  botServiceClient: {
    processMessage: (payload: NormalizedMessage) => Promise<BotServiceResponse>;
  };
  telegramClient: {
    sendMessage: (payload: {
      chatId: string;
      text: string;
      replyToMessageId: string;
    }) => Promise<unknown>;
  };
};

function isTextMessage(
  update: TelegramUpdate,
): update is TelegramUpdate & {
  message: TextMessage;
} {
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

function normalizeMessage(message: TextMessage): NormalizedMessage {
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
  ): Promise<{ status: "ignored" | "replied" | "processed_no_reply" }> {
    if (!isTextMessage(update)) {
      return { status: "ignored" };
    }

    const normalizedMessage = normalizeMessage(update.message);
    const botResponse = await botServiceClient.processMessage(normalizedMessage);

    if (botResponse?.should_reply === true && typeof botResponse.reply_text === "string") {
      await telegramClient.sendMessage({
        chatId: normalizedMessage.chat_id,
        text: botResponse.reply_text,
        replyToMessageId: normalizedMessage.message_id,
      });
      return { status: "replied" };
    }

    return { status: "processed_no_reply" };
  };
}

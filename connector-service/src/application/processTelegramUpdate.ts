import type {
  ProcessImageRequest,
  ProcessMessageRequest,
  ProcessMessageResponse,
} from "../contracts/botService.js";
import type {
  TelegramFileInfo,
  TelegramPhotoMessage,
  TelegramPhotoSize,
  TelegramTextMessage,
  TelegramUpdate,
} from "../contracts/telegram.js";

type ProcessTelegramUpdateOptions = {
  botServiceClient: {
    processMessage: (payload: ProcessMessageRequest) => Promise<ProcessMessageResponse>;
    processImage: (payload: ProcessImageRequest) => Promise<ProcessMessageResponse>;
  };
  telegramClient: {
    sendMessage: (payload: {
      chatId: string;
      text: string;
      replyToMessageId: string;
    }) => Promise<unknown>;
    getFile: (fileId: string) => Promise<TelegramFileInfo>;
    downloadFile: (
      filePath: string,
    ) => Promise<{ bytes: Uint8Array; mimeType: string }>;
  };
};

export type ProcessTelegramUpdateResult =
  | "ignored"
  | "replied"
  | "processed_no_reply";

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

function isPhotoMessage(
  update: TelegramUpdate,
): update is TelegramUpdate & { message: TelegramPhotoMessage } {
  return (
    Array.isArray(update?.message?.photo) &&
    update.message.photo.length > 0 &&
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

function pickLargestPhoto(photos: TelegramPhotoSize[]): TelegramPhotoSize {
  // Telegram convention: sizes are listed smallest → largest.
  // Defensive: pick the one with the largest area instead of trusting order.
  return photos.reduce((largest, candidate) =>
    candidate.width * candidate.height > largest.width * largest.height
      ? candidate
      : largest,
  );
}

function bytesToBase64(bytes: Uint8Array): string {
  // Buffer is available in Node by default; avoids loading a polyfill.
  return Buffer.from(bytes).toString("base64");
}

function normalizeText(message: TelegramTextMessage): ProcessMessageRequest {
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
    if (isTextMessage(update)) {
      return await handleText(update.message);
    }
    if (isPhotoMessage(update)) {
      return await handlePhoto(update.message);
    }
    return "ignored";
  };

  async function handleText(
    message: TelegramTextMessage,
  ): Promise<ProcessTelegramUpdateResult> {
    const normalized = normalizeText(message);
    const botResponse = await botServiceClient.processMessage(normalized);
    return await maybeReply(botResponse, normalized.chat_id, normalized.message_id);
  }

  async function handlePhoto(
    message: TelegramPhotoMessage,
  ): Promise<ProcessTelegramUpdateResult> {
    const largest = pickLargestPhoto(message.photo);
    const fileInfo = await telegramClient.getFile(largest.file_id);
    const { bytes, mimeType } = await telegramClient.downloadFile(fileInfo.file_path);

    const payload: ProcessImageRequest = {
      telegram_user_id: String(message.from.id),
      chat_id: String(message.chat.id),
      message_id: String(message.message_id),
      timestamp: toIsoTimestamp(message.date),
      image_data: bytesToBase64(bytes),
      mime_type: mimeType,
    };

    const botResponse = await botServiceClient.processImage(payload);
    return await maybeReply(botResponse, payload.chat_id, payload.message_id);
  }

  async function maybeReply(
    botResponse: ProcessMessageResponse,
    chatId: string,
    replyToMessageId: string,
  ): Promise<ProcessTelegramUpdateResult> {
    if (
      botResponse?.should_reply === true &&
      typeof botResponse.reply_text === "string"
    ) {
      await telegramClient.sendMessage({
        chatId,
        text: botResponse.reply_text,
        replyToMessageId,
      });
      return "replied";
    }
    return "processed_no_reply";
  }
}

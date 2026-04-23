function isTextMessage(update) {
  return (
    typeof update?.message?.text === "string" &&
    update.message.text.trim() !== "" &&
    update.message.from?.id !== undefined &&
    update.message.chat?.id !== undefined &&
    update.message.message_id !== undefined
  );
}

function toIsoTimestamp(unixTimestamp) {
  if (typeof unixTimestamp === "number") {
    return new Date(unixTimestamp * 1000).toISOString();
  }
  return new Date().toISOString();
}

function normalizeMessage(update) {
  return {
    telegram_user_id: String(update.message.from.id),
    chat_id: String(update.message.chat.id),
    message_text: update.message.text,
    message_id: String(update.message.message_id),
    timestamp: toIsoTimestamp(update.message.date),
  };
}

export function createProcessTelegramUpdate({ botServiceClient, telegramClient }) {
  return async function processTelegramUpdate(update) {
    if (!isTextMessage(update)) {
      return { status: "ignored" };
    }

    const normalizedMessage = normalizeMessage(update);
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

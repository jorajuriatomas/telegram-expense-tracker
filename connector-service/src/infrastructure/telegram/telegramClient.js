export class TelegramClient {
  constructor({ apiBaseUrl, botToken, fetchImpl = fetch }) {
    this.fetch = fetchImpl;
    this.sendMessageUrl = new URL(`/bot${botToken}/sendMessage`, apiBaseUrl).toString();
  }

  async sendMessage({ chatId, text, replyToMessageId }) {
    const response = await this.fetch(this.sendMessageUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        reply_to_message_id: Number.parseInt(replyToMessageId, 10),
      }),
    });

    if (!response.ok) {
      throw new Error(`Telegram API returned status ${response.status}`);
    }

    return response.json();
  }
}

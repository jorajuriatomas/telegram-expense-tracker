export class TelegramClient {
  private fetch: typeof fetch;
  private sendMessageUrl: string;

  constructor({
    apiBaseUrl,
    botToken,
    fetchImpl = fetch,
  }: {
    apiBaseUrl: string;
    botToken: string;
    fetchImpl?: typeof fetch;
  }) {
    this.fetch = fetchImpl;
    this.sendMessageUrl = new URL(`/bot${botToken}/sendMessage`, apiBaseUrl).toString();
  }

  async sendMessage({
    chatId,
    text,
    replyToMessageId,
  }: {
    chatId: string;
    text: string;
    replyToMessageId: string;
  }): Promise<unknown> {
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

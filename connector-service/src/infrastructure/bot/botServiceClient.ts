export type ProcessMessagePayload = {
  telegram_user_id: string;
  chat_id: string;
  message_text: string;
  message_id: string;
  timestamp: string;
};

export type ProcessMessageResponse = {
  should_reply?: boolean;
  reply_text?: string | null;
};

export class BotServiceClient {
  private fetch: typeof fetch;
  private processMessageUrl: string;

  constructor({
    baseUrl,
    processMessagePath,
    fetchImpl = fetch,
  }: {
    baseUrl: string;
    processMessagePath: string;
    fetchImpl?: typeof fetch;
  }) {
    this.fetch = fetchImpl;
    this.processMessageUrl = new URL(processMessagePath, baseUrl).toString();
  }

  async processMessage(payload: ProcessMessagePayload): Promise<ProcessMessageResponse> {
    const response = await this.fetch(this.processMessageUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Bot Service returned status ${response.status}: ${errorBody}`);
    }

    return (await response.json()) as ProcessMessageResponse;
  }
}

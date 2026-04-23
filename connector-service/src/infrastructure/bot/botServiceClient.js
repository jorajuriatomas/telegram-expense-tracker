export class BotServiceClient {
  constructor({ baseUrl, processMessagePath, fetchImpl = fetch }) {
    this.fetch = fetchImpl;
    this.processMessageUrl = new URL(processMessagePath, baseUrl).toString();
  }

  async processMessage(payload) {
    const response = await this.fetch(this.processMessageUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Bot Service returned status ${response.status}`);
    }

    return response.json();
  }
}

import type {
  ProcessMessageRequest,
  ProcessMessageResponse,
} from "../../contracts/botService.js";

/**
 * HTTP client for the Bot Service `/process-message` endpoint.
 *
 * Request and response types are imported from `contracts/botService` —
 * the same module the use case uses to build the payload. This guarantees
 * the wire format never drifts between caller and transport.
 */
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

  async processMessage(payload: ProcessMessageRequest): Promise<ProcessMessageResponse> {
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

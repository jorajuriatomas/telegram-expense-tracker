import type {
  ProcessImageRequest,
  ProcessMessageRequest,
  ProcessMessageResponse,
} from "../../contracts/botService.js";

/**
 * HTTP client for the Bot Service.
 *
 * Two endpoints are exposed: text (`/process-message`) and image
 * (`/process-image`). Both share the same response shape. Request and
 * response types are imported from `contracts/botService` — the same
 * module the use case uses to build payloads. This guarantees the wire
 * format never drifts between caller and transport.
 */
export class BotServiceClient {
  private fetch: typeof fetch;
  private processMessageUrl: string;
  private processImageUrl: string;

  constructor({
    baseUrl,
    processMessagePath,
    processImagePath = "/process-image",
    fetchImpl = fetch,
  }: {
    baseUrl: string;
    processMessagePath: string;
    processImagePath?: string;
    fetchImpl?: typeof fetch;
  }) {
    this.fetch = fetchImpl;
    this.processMessageUrl = new URL(processMessagePath, baseUrl).toString();
    this.processImageUrl = new URL(processImagePath, baseUrl).toString();
  }

  async processMessage(payload: ProcessMessageRequest): Promise<ProcessMessageResponse> {
    return this._postJson(this.processMessageUrl, payload);
  }

  async processImage(payload: ProcessImageRequest): Promise<ProcessMessageResponse> {
    return this._postJson(this.processImageUrl, payload);
  }

  private async _postJson<T>(url: string, body: unknown): Promise<T> {
    const response = await this.fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Bot Service returned status ${response.status}: ${errorBody}`);
    }

    return (await response.json()) as T;
  }
}

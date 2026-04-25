import type { TelegramFileInfo } from "../../contracts/telegram.js";

/**
 * HTTP client for the Telegram Bot API.
 *
 * Telegram exposes two distinct base URLs:
 *  - The API base (e.g. `https://api.telegram.org`) for method calls,
 *    accessed as `/bot<TOKEN>/<method>`.
 *  - A file CDN at the same host but with a `/file/bot<TOKEN>/<path>`
 *    prefix, used to download the actual bytes after `getFile` returns
 *    a `file_path`.
 *
 * This client keeps both URLs derived from a single `apiBaseUrl` env var,
 * so a single setting controls the whole Telegram surface.
 */
export class TelegramClient {
  private fetch: typeof fetch;
  private sendMessageUrl: string;
  private getFileUrl: string;
  private fileDownloadBaseUrl: string;

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
    this.getFileUrl = new URL(`/bot${botToken}/getFile`, apiBaseUrl).toString();
    this.fileDownloadBaseUrl = new URL(`/file/bot${botToken}/`, apiBaseUrl).toString();
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

  /**
   * Look up a file's storage path. Telegram returns a `file_path` (e.g.
   * `photos/file_42.jpg`) that we then append to the file CDN base URL
   * to actually download the bytes.
   */
  async getFile(fileId: string): Promise<TelegramFileInfo> {
    const url = `${this.getFileUrl}?file_id=${encodeURIComponent(fileId)}`;
    const response = await this.fetch(url);
    if (!response.ok) {
      throw new Error(`Telegram getFile returned status ${response.status}`);
    }
    const body = (await response.json()) as { ok: boolean; result?: TelegramFileInfo };
    if (!body.ok || !body.result) {
      throw new Error(`Telegram getFile returned non-ok body for file_id=${fileId}`);
    }
    return body.result;
  }

  /**
   * Download the bytes of a previously-resolved file.
   *
   * Telegram's file CDN typically serves photos with a generic
   * `Content-Type: application/octet-stream` rather than the actual
   * image type. Since Telegram only stores photo uploads as JPEG, we
   * fall back to `image/jpeg` for any non-image response header. This
   * keeps downstream multimodal LLM clients (which validate the
   * `data:image/...` prefix) happy without sniffing magic bytes.
   */
  async downloadFile(filePath: string): Promise<{ bytes: Uint8Array; mimeType: string }> {
    const url = new URL(filePath, this.fileDownloadBaseUrl).toString();
    const response = await this.fetch(url);
    if (!response.ok) {
      throw new Error(`Telegram file download returned status ${response.status}`);
    }
    const arrayBuffer = await response.arrayBuffer();
    const rawMime = response.headers.get("content-type") ?? "";
    const mimeType = rawMime.startsWith("image/") ? rawMime : "image/jpeg";
    return { bytes: new Uint8Array(arrayBuffer), mimeType };
  }
}

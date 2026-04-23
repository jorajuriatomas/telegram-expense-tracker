import test from "node:test";
import assert from "node:assert/strict";
import type { Server } from "node:http";
import type { Express, Request, Response } from "express";

import { createApp } from "../src/app.js";

async function withServer(app: Express, callback: (baseUrl: string) => Promise<void>) {
  const server = await new Promise<Server>((resolve) => {
    const createdServer = app.listen(0, () => resolve(createdServer));
  });

  try {
    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("Unexpected server address type");
    }
    const baseUrl = `http://127.0.0.1:${address.port}`;
    await callback(baseUrl);
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error?: Error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
}

test("GET /health returns connector service status", async () => {
  const app = createApp({
    telegramWebhookPath: "/telegram/webhook",
    telegramWebhookHandler: async (_req: Request, res: Response) =>
      res.status(200).json({ status: "ok" }),
  });

  await withServer(app, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/health`);
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.deepEqual(body, { status: "ok", service: "connector-service" });
  });
});

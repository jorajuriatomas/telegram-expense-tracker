import test from "node:test";
import assert from "node:assert/strict";

import { createApp } from "../src/app.js";

async function withServer(app, callback) {
  const server = await new Promise((resolve) => {
    const createdServer = app.listen(0, () => resolve(createdServer));
  });

  try {
    const address = server.address();
    const baseUrl = `http://127.0.0.1:${address.port}`;
    await callback(baseUrl);
  } finally {
    await new Promise((resolve, reject) => {
      server.close((error) => {
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
    telegramWebhookHandler: async (_req, res) => res.status(200).json({ status: "ok" }),
  });

  await withServer(app, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/health`);
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.deepEqual(body, { status: "ok", service: "connector-service" });
  });
});

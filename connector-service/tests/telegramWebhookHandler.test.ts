import test from "node:test";
import assert from "node:assert/strict";

import { createTelegramWebhookHandler } from "../src/interface/http/telegramWebhookHandler.js";

function createMockResponse() {
  return {
    statusCode: 200,
    body: null as unknown,
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(payload: unknown) {
      this.body = payload;
      return this;
    },
  };
}

function nextTick(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

test("rejects webhook request when Telegram secret is invalid", async () => {
  const handler = createTelegramWebhookHandler({
    webhookSecret: "expected-secret",
    processTelegramUpdate: async () => {
      throw new Error("Should not be called");
    },
  });

  const req = {
    body: {},
    get: () => "invalid-secret",
  };
  const res = createMockResponse();

  handler(req as never, res as never, (() => {}) as never);

  assert.equal(res.statusCode, 401);
  assert.deepEqual(res.body, { error: "unauthorized" });
});

test("ACKs webhook request immediately and processes update in background", async () => {
  let processed = false;
  let resolveProcessing: (() => void) | undefined;
  const processingStarted = new Promise<void>((resolve) => {
    resolveProcessing = resolve;
  });

  const handler = createTelegramWebhookHandler({
    webhookSecret: "expected-secret",
    processTelegramUpdate: async () => {
      processed = true;
      resolveProcessing?.();
    },
  });

  const req = {
    body: { update_id: 42 },
    get: () => "expected-secret",
  };
  const res = createMockResponse();

  handler(req as never, res as never, (() => {}) as never);

  // Webhook is ACKed synchronously, before the background work runs.
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { status: "ok" });

  await processingStarted;
  await nextTick();
  assert.equal(processed, true);
});

test("background processing failures do not crash the handler", async () => {
  const handler = createTelegramWebhookHandler({
    webhookSecret: "expected-secret",
    processTelegramUpdate: async () => {
      throw new Error("downstream failure");
    },
  });

  const req = {
    body: {},
    get: () => "expected-secret",
  };
  const res = createMockResponse();

  handler(req as never, res as never, (() => {}) as never);

  assert.equal(res.statusCode, 200);
  await nextTick();
  await nextTick();
});

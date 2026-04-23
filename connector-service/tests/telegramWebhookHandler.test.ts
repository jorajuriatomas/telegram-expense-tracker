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

  await handler(req as never, res as never, (() => {}) as never);

  assert.equal(res.statusCode, 401);
  assert.deepEqual(res.body, { error: "unauthorized" });
});

test("accepts webhook request and processes update with valid secret", async () => {
  let processed = false;

  const handler = createTelegramWebhookHandler({
    webhookSecret: "expected-secret",
    processTelegramUpdate: async () => {
      processed = true;
    },
  });

  const req = {
    body: { update_id: 42 },
    get: () => "expected-secret",
  };
  const res = createMockResponse();

  await handler(req as never, res as never, (() => {}) as never);

  assert.equal(processed, true);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { status: "ok" });
});

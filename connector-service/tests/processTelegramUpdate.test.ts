import test from "node:test";
import assert from "node:assert/strict";

import { createProcessTelegramUpdate } from "../src/application/processTelegramUpdate.js";
import type { ProcessMessageRequest } from "../src/contracts/botService.js";

type TelegramSendPayload = {
  chatId: string;
  text: string;
  replyToMessageId: string;
};

function buildUpdate(messageOverrides: Record<string, unknown> = {}) {
  return {
    message: {
      message_id: 101,
      date: 1711111111,
      text: "Pizza 20 bucks",
      from: { id: 12345 },
      chat: { id: 98765 },
      ...messageOverrides,
    },
  };
}

test("ignores updates without text message", async () => {
  let botCalled = false;
  let telegramCalled = false;

  const processTelegramUpdate = createProcessTelegramUpdate({
    botServiceClient: {
      async processMessage() {
        botCalled = true;
        return {};
      },
    },
    telegramClient: {
      async sendMessage() {
        telegramCalled = true;
      },
    },
  });

  const result = await processTelegramUpdate({ message: { photo: [{ file_id: "1" }] } });

  assert.equal(result, "ignored");
  assert.equal(botCalled, false);
  assert.equal(telegramCalled, false);
});

test("forwards normalized message to bot service and sends Telegram reply", async () => {
  const botPayloads: ProcessMessageRequest[] = [];
  const telegramPayloads: TelegramSendPayload[] = [];

  const processTelegramUpdate = createProcessTelegramUpdate({
    botServiceClient: {
      async processMessage(payload: ProcessMessageRequest) {
        botPayloads.push(payload);
        return {
          should_reply: true,
          reply_text: "[Food] expense added \u2705",
        };
      },
    },
    telegramClient: {
      async sendMessage(payload: TelegramSendPayload) {
        telegramPayloads.push(payload);
      },
    },
  });

  const result = await processTelegramUpdate(buildUpdate());

  assert.equal(result, "replied");
  assert.equal(botPayloads.length, 1);
  assert.deepEqual(botPayloads[0], {
    telegram_user_id: "12345",
    chat_id: "98765",
    message_text: "Pizza 20 bucks",
    message_id: "101",
    timestamp: new Date(1711111111 * 1000).toISOString(),
  });
  assert.equal(telegramPayloads.length, 1);
  assert.deepEqual(telegramPayloads[0], {
    chatId: "98765",
    text: "[Food] expense added \u2705",
    replyToMessageId: "101",
  });
});

test("does not send Telegram reply when bot says should_reply=false", async () => {
  let telegramCalled = false;

  const processTelegramUpdate = createProcessTelegramUpdate({
    botServiceClient: {
      async processMessage() {
        return {
          should_reply: false,
          reply_text: null,
        };
      },
    },
    telegramClient: {
      async sendMessage() {
        telegramCalled = true;
      },
    },
  });

  const result = await processTelegramUpdate(buildUpdate());

  assert.equal(result, "processed_no_reply");
  assert.equal(telegramCalled, false);
});

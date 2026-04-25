import test from "node:test";
import assert from "node:assert/strict";

import { createProcessTelegramUpdate } from "../src/application/processTelegramUpdate.js";
import type {
  ProcessImageRequest,
  ProcessMessageRequest,
} from "../src/contracts/botService.js";
import type { TelegramFileInfo } from "../src/contracts/telegram.js";

type TelegramSendPayload = {
  chatId: string;
  text: string;
  replyToMessageId: string;
};

function buildTextUpdate(messageOverrides: Record<string, unknown> = {}) {
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

function buildPhotoUpdate(messageOverrides: Record<string, unknown> = {}) {
  return {
    message: {
      message_id: 200,
      date: 1711111111,
      photo: [
        { file_id: "small", file_unique_id: "u1", width: 90, height: 60 },
        { file_id: "medium", file_unique_id: "u2", width: 320, height: 240 },
        { file_id: "large", file_unique_id: "u3", width: 1280, height: 960 },
      ],
      from: { id: 12345 },
      chat: { id: 98765 },
      ...messageOverrides,
    },
  };
}

function makeStubs() {
  const botPayloads: { kind: "text" | "image"; payload: any }[] = [];
  const telegramSends: TelegramSendPayload[] = [];
  const getFileCalls: string[] = [];
  const downloadCalls: string[] = [];

  const botServiceClient = {
    async processMessage(payload: ProcessMessageRequest) {
      botPayloads.push({ kind: "text", payload });
      return { should_reply: true, reply_text: "[Food] expense added \u2705" };
    },
    async processImage(payload: ProcessImageRequest) {
      botPayloads.push({ kind: "image", payload });
      return { should_reply: true, reply_text: "[Food] expense added \u2705" };
    },
  };

  const telegramClient = {
    async sendMessage(payload: TelegramSendPayload) {
      telegramSends.push(payload);
    },
    async getFile(fileId: string): Promise<TelegramFileInfo> {
      getFileCalls.push(fileId);
      return {
        file_id: fileId,
        file_unique_id: "uniq-" + fileId,
        file_size: 1234,
        file_path: `photos/${fileId}.jpg`,
      };
    },
    async downloadFile(filePath: string) {
      downloadCalls.push(filePath);
      return {
        bytes: new Uint8Array([0x89, 0x50, 0x4e, 0x47]),
        mimeType: "image/jpeg",
      };
    },
  };

  return { botServiceClient, telegramClient, botPayloads, telegramSends, getFileCalls, downloadCalls };
}

test("ignores updates without text or photo", async () => {
  const { botServiceClient, telegramClient, botPayloads, telegramSends } = makeStubs();

  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  const result = await processTelegramUpdate({
    message: { sticker: { file_id: "x" } } as never,
  });

  assert.equal(result, "ignored");
  assert.equal(botPayloads.length, 0);
  assert.equal(telegramSends.length, 0);
});

test("forwards normalized text message to bot service and sends Telegram reply", async () => {
  const { botServiceClient, telegramClient, botPayloads, telegramSends } = makeStubs();

  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  const result = await processTelegramUpdate(buildTextUpdate());

  assert.equal(result, "replied");
  assert.equal(botPayloads.length, 1);
  assert.equal(botPayloads[0].kind, "text");
  assert.deepEqual(botPayloads[0].payload, {
    telegram_user_id: "12345",
    chat_id: "98765",
    message_text: "Pizza 20 bucks",
    message_id: "101",
    timestamp: new Date(1711111111 * 1000).toISOString(),
  });
  assert.equal(telegramSends.length, 1);
});

test("does not send Telegram reply when bot says should_reply=false", async () => {
  const { telegramClient, telegramSends } = makeStubs();
  const botServiceClient = {
    async processMessage() {
      return { should_reply: false, reply_text: null };
    },
    async processImage() {
      return { should_reply: false, reply_text: null };
    },
  };

  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  const result = await processTelegramUpdate(buildTextUpdate());

  assert.equal(result, "processed_no_reply");
  assert.equal(telegramSends.length, 0);
});

test("photo: downloads largest size, base64-encodes, and POSTs to /process-image", async () => {
  const { botServiceClient, telegramClient, botPayloads, telegramSends, getFileCalls, downloadCalls } =
    makeStubs();

  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  const result = await processTelegramUpdate(buildPhotoUpdate());

  assert.equal(result, "replied");
  // Picked the largest of the 3 photo sizes (1280x960)
  assert.deepEqual(getFileCalls, ["large"]);
  assert.deepEqual(downloadCalls, ["photos/large.jpg"]);

  assert.equal(botPayloads.length, 1);
  assert.equal(botPayloads[0].kind, "image");
  const sent = botPayloads[0].payload;
  assert.equal(sent.telegram_user_id, "12345");
  assert.equal(sent.chat_id, "98765");
  assert.equal(sent.message_id, "200");
  assert.equal(sent.mime_type, "image/jpeg");
  // Bytes [0x89, 0x50, 0x4e, 0x47] base64 = "iVBORw=="
  assert.equal(sent.image_data, "iVBORw==");

  assert.equal(telegramSends.length, 1);
  assert.equal(telegramSends[0].replyToMessageId, "200");
});

test("photo with single size still works (no need to compare)", async () => {
  const { botServiceClient, telegramClient, getFileCalls } = makeStubs();
  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  await processTelegramUpdate(
    buildPhotoUpdate({
      photo: [{ file_id: "only-one", file_unique_id: "x", width: 100, height: 100 }],
    }),
  );

  assert.deepEqual(getFileCalls, ["only-one"]);
});

test("photo: bot returning should_reply=false means no Telegram reply", async () => {
  const { telegramClient, telegramSends } = makeStubs();
  const botServiceClient = {
    async processMessage() {
      return { should_reply: false, reply_text: null };
    },
    async processImage() {
      return { should_reply: false, reply_text: null };
    },
  };
  const processTelegramUpdate = createProcessTelegramUpdate({ botServiceClient, telegramClient });

  const result = await processTelegramUpdate(buildPhotoUpdate());

  assert.equal(result, "processed_no_reply");
  assert.equal(telegramSends.length, 0);
});

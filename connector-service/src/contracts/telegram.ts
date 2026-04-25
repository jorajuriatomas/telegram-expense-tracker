/**
 * Upstream contract from the Telegram Bot API.
 *
 * Only the subset of the Telegram `Update` payload that the connector
 * actually consumes is modelled here. Treating this as a contract
 * (vs. defining shapes inline in the use case) keeps the parsing /
 * normalization code honest about what it depends on from upstream.
 *
 * Reference: https://core.telegram.org/bots/api#update
 */

/** Narrowed view of a Telegram message we consider processable as text. */
export type TelegramTextMessage = {
  message_id: number;
  /** Unix timestamp (seconds). */
  date?: number;
  text: string;
  from: { id: number | string };
  chat: { id: number | string };
};

/** One element of the `photo` array Telegram sends — multiple sizes per upload. */
export type TelegramPhotoSize = {
  file_id: string;
  file_unique_id: string;
  width: number;
  height: number;
  file_size?: number;
};

/** Narrowed view of a Telegram message that contains a photo. */
export type TelegramPhotoMessage = {
  message_id: number;
  /** Unix timestamp (seconds). */
  date?: number;
  /** Telegram returns multiple sizes; the largest is typically the last. */
  photo: TelegramPhotoSize[];
  /** Optional caption the user added with the photo (we currently ignore it). */
  caption?: string;
  from: { id: number | string };
  chat: { id: number | string };
};

/** Loose shape of an incoming Telegram update. We accept anything and narrow on read. */
export type TelegramUpdate = {
  message?: {
    message_id?: number;
    date?: number;
    text?: string;
    photo?: TelegramPhotoSize[];
    caption?: string;
    from?: { id?: number | string };
    chat?: { id?: number | string };
    [key: string]: unknown;
  };
};

/** Response shape from Telegram's `getFile` endpoint. */
export type TelegramFileInfo = {
  file_id: string;
  file_unique_id: string;
  file_size?: number;
  file_path: string;
};

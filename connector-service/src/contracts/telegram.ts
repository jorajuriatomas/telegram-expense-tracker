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

/** Narrowed view of a Telegram message we consider processable (text-only). */
export type TelegramTextMessage = {
  message_id: number;
  /** Unix timestamp (seconds). */
  date?: number;
  text: string;
  from: { id: number | string };
  chat: { id: number | string };
};

/** Loose shape of an incoming Telegram update. We accept anything and narrow on read. */
export type TelegramUpdate = {
  message?: {
    message_id?: number;
    date?: number;
    text?: string;
    from?: { id?: number | string };
    chat?: { id?: number | string };
    [key: string]: unknown;
  };
};

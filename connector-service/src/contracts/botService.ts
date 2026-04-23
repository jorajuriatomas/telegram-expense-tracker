/**
 * HTTP contract between Connector Service and Bot Service.
 *
 * These shapes mirror the Pydantic models in
 * `bot-service/app/interface/http/schemas.py`. They are the single source
 * of truth for the Connector side of the boundary; both the use case
 * (which builds the request) and the HTTP client (which sends it) import
 * from here. Keeping this in `contracts/` prevents the request/response
 * shapes from drifting between caller and transport layers.
 */

export type ProcessMessageRequest = {
  telegram_user_id: string;
  chat_id: string;
  message_text: string;
  message_id: string;
  /** ISO-8601 string. */
  timestamp: string;
};

export type ProcessMessageResponse = {
  should_reply?: boolean;
  reply_text?: string | null;
};

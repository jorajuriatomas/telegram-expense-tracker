from datetime import datetime

from pydantic import BaseModel, Field


class ProcessMessageRequest(BaseModel):
    """Text-message payload received from the connector."""

    telegram_user_id: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    message_text: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    timestamp: datetime


class ProcessImageRequest(BaseModel):
    """Image-message payload (e.g. receipt photo) received from the connector.

    `image_data` is the raw bytes of the image, base64-encoded so the payload
    stays JSON. `mime_type` lets the LLM hint at decoding (typically
    `image/jpeg` from Telegram).
    """

    telegram_user_id: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    timestamp: datetime
    image_data: str = Field(min_length=1, description="Base64-encoded image bytes")
    mime_type: str = Field(default="image/jpeg")


class ProcessMessageResponse(BaseModel):
    """Shared response shape for both text and image processing endpoints."""

    should_reply: bool
    reply_text: str | None = None

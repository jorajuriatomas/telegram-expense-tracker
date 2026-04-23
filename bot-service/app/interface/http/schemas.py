from datetime import datetime

from pydantic import BaseModel, Field


class ProcessMessageRequest(BaseModel):
    telegram_user_id: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    message_text: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    timestamp: datetime


class ProcessMessageResponse(BaseModel):
    should_reply: bool
    reply_text: str | None = None

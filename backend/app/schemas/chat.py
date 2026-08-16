"""对话 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    fund_ids: list[str] = Field(default_factory=list, max_length=10)
    conversation_id: str | None = Field(default=None, max_length=36)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    fund_ids: list[str] = Field(default_factory=list, max_length=10)

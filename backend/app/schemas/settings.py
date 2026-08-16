"""设置 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LLMSettings(BaseModel):
    provider: str = Field(default="deepseek", max_length=32)
    model: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=256)


class NotificationSettings(BaseModel):
    email_enabled: bool = False
    email_to: EmailStr | None = None
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class SyncSettings(BaseModel):
    quote_interval_minutes: int = Field(default=5, ge=1, le=60)


class SettingsUpdate(BaseModel):
    llm: LLMSettings | None = None
    notifications: NotificationSettings | None = None
    sync: SyncSettings | None = None


class KeySetRequest(BaseModel):
    deepseek_api_key: str = Field(min_length=8, max_length=256)

"""自选基金 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    fund_code: str = Field(min_length=1, max_length=16)
    group_name: str = Field(default="默认", max_length=32)
    pinned: bool = False


class WatchlistUpdate(BaseModel):
    group_name: str | None = Field(default=None, max_length=32)
    pinned: bool | None = None

"""分析请求 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    fund_ids: list[str] = Field(min_length=1, max_length=10)
    time_range: str = Field(default="3M", pattern="^(1M|3M|6M|1Y|3Y)$")

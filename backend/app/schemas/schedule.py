"""定时分析 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ScheduleBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    schedule_type: str = Field(pattern="^(daily|weekly|monthly|cron)$")
    time_of_day: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_of_week: int | None = Field(default=None, ge=0, le=6)  # 0=周一
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    cron_expression: str | None = Field(default=None, max_length=64)
    fund_ids: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True
    notification_channels: list[str] = Field(default_factory=lambda: ["in_app"])
    llm_summary: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.schedule_type == "cron" and not self.cron_expression:
            raise ValueError("cron 类型必须提供 cron_expression")
        if self.schedule_type != "cron" and not self.time_of_day:
            raise ValueError("必须提供 time_of_day（HH:MM）")
        return self


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    schedule_type: str | None = Field(default=None, pattern="^(daily|weekly|monthly|cron)$")
    time_of_day: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    cron_expression: str | None = Field(default=None, max_length=64)
    fund_ids: list[str] | None = Field(default=None, max_length=50)
    enabled: bool | None = None
    notification_channels: list[str] | None = None
    llm_summary: bool | None = None

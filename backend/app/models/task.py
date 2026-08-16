"""任务相关模型：TaskRun / ScheduledAnalysis / Report。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending / running / success / failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScheduledAnalysis(Base):
    __tablename__ = "scheduled_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    schedule_type: Mapped[str] = mapped_column(String(16))  # daily/weekly/monthly/cron
    cron_expression: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "HH:MM"
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=周一
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fund_ids: Mapped[list] = mapped_column(JSON, default=list)  # 基金代码列表
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_channels: Mapped[list] = mapped_column(JSON, default=list)  # ["in_app","email"]
    llm_summary: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(256))
    content_md: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual/scheduled
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

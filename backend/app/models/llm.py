"""LLM 相关模型：Conversation / Message / AnalysisSnapshot。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4 hex
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    fund_codes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 注入的 Context 快照
    context_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)  # Context 内容指纹
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisSnapshot(Base):
    """预测结果快照：保留模型版本，重新训练不影响历史结果。"""

    __tablename__ = "analysis_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("funds.id", ondelete="CASCADE"), index=True
    )
    model_version: Mapped[str] = mapped_column(String(16), default="v0.1")
    horizon: Mapped[str] = mapped_column(String(16))  # short/medium/long
    horizon_days: Mapped[int] = mapped_column(Float, default=5)
    prob_up: Mapped[float] = mapped_column(Float)
    prob_range: Mapped[float] = mapped_column(Float)
    prob_down: Mapped[float] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    factors_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

"""新闻与政策模型。所有内容保留来源与链接，禁止编造。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="mock")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    related_fund: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1..1
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="mock")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 发布部门
    policy_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    impact_score: Mapped[float] = mapped_column(Float, default=0.5)  # 预计影响强度 0..1
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

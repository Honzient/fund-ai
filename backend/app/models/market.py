"""市场指数模型：MarketIndex / MarketIndexData。可继续增加指数。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.dates import utcnow


class MarketIndex(Base):
    __tablename__ = "market_indexes"

    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    index_name: Mapped[str] = mapped_column(String(64))
    market: Mapped[str | None] = mapped_column(String(16), nullable=True)  # CN/US/HK
    latest_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    data: Mapped[list["MarketIndexData"]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )


class MarketIndexData(Base):
    __tablename__ = "market_index_data"
    __table_args__ = (
        UniqueConstraint("index_id", "date", name="uq_index_date"),
        Index("ix_index_date", "index_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_id: Mapped[int] = mapped_column(
        ForeignKey("market_indexes.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    index: Mapped["MarketIndex"] = relationship(back_populates="data")

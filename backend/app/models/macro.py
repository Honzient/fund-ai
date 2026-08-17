"""宏观数据模型。指标可扩展：GDP/CPI/PPI/PMI/利率/社融/M2/汇率/国债收益率/失业率/大宗商品等。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class MacroData(Base):
    __tablename__ = "macro_data"
    __table_args__ = (UniqueConstraint("indicator", "period", name="uq_macro_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period: Mapped[str] = mapped_column(String(16))  # 如 2026-05 或 2026Q2
    change: Mapped[float | None] = mapped_column(Float, nullable=True)  # 环比/同比变化
    source: Mapped[str] = mapped_column(String(32), default="mock")
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    quality: Mapped[str | None] = mapped_column(String(16), nullable=True)  # high/medium/low
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

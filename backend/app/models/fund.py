"""基金相关模型：Fund / FundDailyData / FundHolding。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.dates import utcnow


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    fund_name: Mapped[str] = mapped_column(String(128), index=True)
    fund_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manager: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    establish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    benchmark: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    management_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    purchase_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    redemption_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    fund_size: Mapped[float | None] = mapped_column(Float, nullable=True)  # 规模（亿元）
    latest_nav: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_nav_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    daily_data: Mapped[list["FundDailyData"]] = relationship(
        back_populates="fund", cascade="all, delete-orphan"
    )
    holdings: Mapped[list["FundHolding"]] = relationship(
        back_populates="fund", cascade="all, delete-orphan"
    )


class FundDailyData(Base):
    __tablename__ = "fund_daily_data"
    __table_args__ = (
        UniqueConstraint("fund_id", "date", name="uq_fund_daily_fund_date"),
        Index("ix_fund_daily_fund_date", "fund_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("funds.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    nav: Mapped[float] = mapped_column(Float)
    accumulated_nav: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_return: Mapped[float | None] = mapped_column(Float, nullable=True)  # 小数（0.0123 = +1.23%）
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fund: Mapped["Fund"] = relationship(back_populates="daily_data")


class FundHolding(Base):
    __tablename__ = "fund_holdings"
    __table_args__ = (
        UniqueConstraint("fund_id", "report_date", "stock_code", name="uq_holding"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("funds.id", ondelete="CASCADE"), index=True
    )
    report_date: Mapped[date] = mapped_column(Date)
    stock_code: Mapped[str] = mapped_column(String(16))
    stock_name: Mapped[str] = mapped_column(String(64))
    weight: Mapped[float] = mapped_column(Float)  # 百分比（9.8 = 9.8%）
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 亿元
    source: Mapped[str] = mapped_column(String(32), default="mock")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fund: Mapped["Fund"] = relationship(back_populates="holdings")

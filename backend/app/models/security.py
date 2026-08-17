"""证券与行业分类模型（行业分类体系，替代硬编码字典）。

支持多分类体系（申万/中信/GICS/Custom），带有效期与来源。
暂无行业数据的证券 → industry="unknown"，不强行归入"其他"。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class SecurityIndustry(Base):
    __tablename__ = "security_industries"

    id: Mapped[int] = mapped_column(primary_key=True)
    security_code: Mapped[str] = mapped_column(String(16), index=True)
    security_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market: Mapped[str | None] = mapped_column(String(16), nullable=True)  # CN/HK/US
    industry: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    taxonomy: Mapped[str] = mapped_column(String(32), default="custom")  # 申万/中信/GICS/custom
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="builtin")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def industry_of(db, security_code: str, as_of: date | None = None, taxonomy: str | None = None) -> str | None:
    """查询证券行业（按有效期与分类体系）；无记录返回 None（调用方标注 unknown）。"""
    from app.utils.dates import today

    as_of = as_of or today()
    q = db.query(SecurityIndustry).filter(SecurityIndustry.security_code == security_code)
    if taxonomy:
        q = q.filter(SecurityIndustry.taxonomy == taxonomy)
    row = (
        q.filter(
            (SecurityIndustry.valid_from.is_(None)) | (SecurityIndustry.valid_from <= as_of),
            (SecurityIndustry.valid_to.is_(None)) | (SecurityIndustry.valid_to >= as_of),
        )
        .order_by(SecurityIndustry.id.desc())
        .first()
    )
    return row.industry if row else None

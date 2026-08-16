"""数据同步编排服务（DataSyncManager 语义）。"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services import fund_service, market_service, news_service
from app.tasks.pipeline import sync_all_data, sync_quotes

log = get_logger("app.data")


def sync_fund_full(fund_code: str) -> dict:
    db = SessionLocal()
    try:
        history = fund_service.sync_fund_history(db, fund_code)
        holdings = fund_service.sync_holdings(db, fund_code)
        return {"history": history, "holdings": holdings}
    finally:
        db.close()


def sync_market() -> dict:
    db = SessionLocal()
    try:
        market_service.ensure_indexes(db)
        results = []
        for code, _name, _mkt in market_service.DEFAULT_INDEXES:
            results.append({"index_code": code, **market_service.sync_index_history(db, code)})
        return {"status": "done", "indexes": results}
    finally:
        db.close()


def sync_news_policies() -> dict:
    db = SessionLocal()
    try:
        return {
            "news": news_service.sync_news(db),
            "policies": news_service.sync_policies(db),
        }
    finally:
        db.close()


__all__ = ["sync_all_data", "sync_quotes", "sync_fund_full", "sync_market", "sync_news_policies"]

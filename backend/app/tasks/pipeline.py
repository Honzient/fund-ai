"""任务流水线：数据同步 / 定时分析 / 报告生成 / 通知发送。"""
from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Fund, ScheduledAnalysis, User
from app.notification import NotificationManager
from app.services import analysis_service, fund_service, market_service, news_service
from app.services.report_service import build_daily_report
from app.utils.dates import now_local, utcnow

log = get_logger("app.task")


def sync_all_data() -> dict:
    """全量/增量数据同步：基金净值、指数、宏观、新闻、政策。"""
    db = SessionLocal()
    stats: dict = {"funds": [], "indexes": [], "macro": {}, "news": {}, "policies": {}}
    try:
        market_service.ensure_indexes(db)
        codes = fund_service.all_fund_codes(db)
        for code in codes:
            try:
                result = fund_service.sync_fund_history(db, code)
                stats["funds"].append({"fund_code": code, **result})
                fund_service.sync_holdings(db, code)
            except Exception as exc:  # noqa: BLE001
                log.warning("基金 %s 同步失败: %s", code, exc)
                stats["funds"].append({"fund_code": code, "status": "failed", "reason": str(exc)[:200]})
        for code in market_service.DEFAULT_INDEXES:
            code = code[0]
            try:
                result = market_service.sync_index_history(db, code)
                stats["indexes"].append({"index_code": code, **result})
            except Exception as exc:  # noqa: BLE001
                stats["indexes"].append({"index_code": code, "status": "failed"})
        try:
            stats["macro"] = sync_macro(db)
        except Exception as exc:  # noqa: BLE001
            stats["macro"] = {"status": "failed", "reason": str(exc)[:200]}
        try:
            stats["news"] = news_service.sync_news(db)
        except Exception as exc:  # noqa: BLE001
            stats["news"] = {"status": "failed", "reason": str(exc)[:200]}
        try:
            stats["policies"] = news_service.sync_policies(db)
        except Exception as exc:  # noqa: BLE001
            stats["policies"] = {"status": "failed", "reason": str(exc)[:200]}
    finally:
        db.close()
    return stats


def sync_macro(db) -> dict:
    from app.models import MacroData
    from app.providers import get_registry
    from app.utils.asyncs import run_async

    items = run_async(get_registry().call("get_macro", limit=300, default=[]))
    added = 0
    for item in items:
        exists = (
            db.query(MacroData.id)
            .filter(MacroData.indicator == item.indicator, MacroData.period == item.period)
            .first()
        )
        if exists:
            continue
        db.add(
            MacroData(
                indicator=item.indicator,
                value=item.value,
                unit=item.unit,
                period=item.period,
                change=item.change,
                source=item.source,
                published_at=item.published_at,
                retrieved_at=utcnow(),
            )
        )
        added += 1
    db.commit()
    return {"status": "synced", "new_rows": added}


def sync_quotes() -> dict:
    """刷新盘中估值缓存（每 N 分钟任务；仅交易时段内请求数据源）。"""
    from app.cache.cache import get_cache
    from app.providers import get_registry
    from app.services.fund_service import _is_trading_session
    from app.utils.asyncs import run_async

    if not _is_trading_session():
        return {"status": "skipped", "reason": "非交易时段"}

    db = SessionLocal()
    try:
        codes = fund_service.all_fund_codes(db)
    finally:
        db.close()
    cache = get_cache()
    updated = 0
    for code in codes:
        key = f"est:{code}"
        if cache.get(key) is not None:
            continue  # 缓存有效期内不重复请求
        est = run_async(get_registry().call_first("get_estimate", fund_code=code))
        if est is not None:
            cache.set(
                key,
                {
                    "available": True,
                    "estimate_nav": float(est.nav),
                    "estimate_return": float(est.return_pct),
                    "estimate_time": est.time.isoformat() if est.time else None,
                    "source": est.source,
                },
                ttl=300,
            )
            updated += 1
        else:
            cache.set(key, {"available": False}, ttl=180)
    log.info("行情估值刷新完成: %d/%d", updated, len(codes))
    return {"status": "done", "updated": updated, "total": len(codes)}


def run_scheduled_analysis(schedule_id: int) -> dict:
    """定时分析任务：获取最新数据 → 量化分析 → LLM 总结 → 生成报告 → 发送通知。"""
    settings = get_settings()
    db = SessionLocal()
    try:
        schedule = db.get(ScheduledAnalysis, schedule_id)
        if schedule is None or not schedule.enabled:
            return {"status": "skipped", "reason": "任务不存在或已禁用"}
        user = db.get(User, schedule.user_id)
        fund_codes = list(schedule.fund_ids or [])
        # 1) 同步最新数据
        for code in fund_codes:
            try:
                fund_service.sync_fund_history(db, code)
            except Exception as exc:  # noqa: BLE001
                log.warning("定时任务数据同步失败 %s: %s", code, exc)
        # 2) 生成报告
        report = build_daily_report(
            db,
            schedule.user_id,
            fund_codes=fund_codes,
            trigger="scheduled",
            llm_summary=bool(schedule.llm_summary),
        )
        # 3) 通知
        channels = list(schedule.notification_channels or ["in_app"])
        if channels:
            NotificationManager().notify(
                user_id=schedule.user_id,
                title=f"定时分析报告：{schedule.name}",
                content=f"报告「{report.title}」已生成。点击查看。",
                type="report",
                channels=channels,
            )
        schedule.last_run_at = utcnow()
        db.commit()
        return {"status": "done", "report_id": report.id, "funds": len(fund_codes)}
    finally:
        db.close()


def generate_report_for_user(user_id: int, fund_codes: list[str] | None = None) -> dict:
    db = SessionLocal()
    try:
        if not fund_codes:
            from app.models import Watchlist

            fund_codes = [
                row[0]
                for row in db.query(Fund.fund_code)
                .join(Watchlist, Watchlist.fund_id == Fund.id)
                .filter(Watchlist.user_id == user_id)
                .all()
            ]
        report = build_daily_report(db, user_id, fund_codes=fund_codes, trigger="manual")
        return {"status": "done", "report_id": report.id}
    finally:
        db.close()

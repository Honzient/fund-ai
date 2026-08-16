"""演示数据种子：离线可用（MockProvider 确定性生成），保证首次启动即可完整演示。

真实数据源（Eastmoney）可用时，通过「立即更新」或定时任务增量同步真实数据并合并。
所有演示数据 source="mock"，前端显示「最新可用数据」。
"""
from __future__ import annotations

import hashlib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import (
    Fund,
    FundDailyData,
    FundHolding,
    MacroData,
    MarketIndex,
    MarketIndexData,
    News,
    Notification,
    Policy,
    User,
    Watchlist,
)
from app.providers.mock_provider import MOCK_FUNDS, MockProvider
from app.services.market_service import DEFAULT_INDEXES
from app.utils.asyncs import run_async
from app.utils.dates import utcnow

log = get_logger("app.data")

DEMO_WATCHLIST = [
    ("110022", "核心基金", True),
    ("005827", "核心基金", False),
    ("161725", "消费", False),
    ("519674", "科技", False),
    ("003096", "医药", False),
    ("000032", "债券", False),
]


def _news_hash(title: str, source: str) -> str:
    return hashlib.sha1(f"{title}|{source}".encode("utf-8")).hexdigest()


def seed_demo_data(db) -> dict:
    settings = get_settings()
    if not settings.SEED_DEMO_DATA:
        return {"seeded": False, "reason": "SEED_DEMO_DATA=false"}
    if db.query(Fund.id).first() is not None:
        return {"seeded": False, "reason": "数据库已有基金数据，跳过"}
    mock = MockProvider()
    log.info("开始注入演示数据（MockProvider，确定性生成）…")

    # 1) 演示用户
    user = db.query(User).filter(User.username == settings.DEMO_USERNAME).first()
    if user is None:
        user = User(
            username=settings.DEMO_USERNAME,
            password_hash=hash_password(settings.DEMO_PASSWORD),
            email=settings.DEMO_EMAIL,
            display_name="演示用户",
        )
        db.add(user)
        db.flush()
        log.info("演示账号已创建: %s", settings.DEMO_USERNAME)

    # 2) 基金 + 净值 + 持仓
    fund_ids: dict[str, int] = {}
    for meta in MOCK_FUNDS:
        code = meta["code"]
        info = run_async(mock.get_fund_info(code))
        if info is None:
            continue
        fund = Fund(
            fund_code=info.fund_code,
            fund_name=info.fund_name,
            fund_type=info.fund_type,
            manager=info.manager,
            company=info.company,
            establish_date=info.establish_date,
            benchmark=info.benchmark,
            risk_level=info.risk_level,
            management_fee=info.management_fee,
            purchase_fee=info.purchase_fee,
            redemption_fee=info.redemption_fee,
            fund_size=info.fund_size,
            source="mock",
            retrieved_at=utcnow(),
        )
        db.add(fund)
        db.flush()
        fund_ids[code] = fund.id
        points = run_async(mock.get_nav_history(code))
        for p in points:
            db.add(
                FundDailyData(
                    fund_id=fund.id,
                    date=p.date,
                    nav=p.nav,
                    accumulated_nav=p.accumulated_nav,
                    daily_return=p.daily_return,
                    volume=p.volume,
                    source="mock",
                    retrieved_at=utcnow(),
                )
            )
        for h in run_async(mock.get_holdings(code)):
            db.add(
                FundHolding(
                    fund_id=fund.id,
                    report_date=h.report_date,
                    stock_code=h.stock_code,
                    stock_name=h.stock_name,
                    weight=h.weight,
                    industry=h.industry,
                    market_value=h.market_value,
                    source="mock",
                    retrieved_at=utcnow(),
                )
            )
        if points:
            fund.latest_nav = points[-1].nav
            fund.latest_nav_date = points[-1].date

    # 3) 指数
    for code, name, market in DEFAULT_INDEXES:
        idx = MarketIndex(index_code=code, index_name=name, market=market, source="mock")
        db.add(idx)
        db.flush()
        bars = run_async(mock.get_index_history(code))
        for bar in bars:
            db.add(
                MarketIndexData(
                    index_id=idx.id,
                    date=bar.date,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    source="mock",
                    retrieved_at=utcnow(),
                )
            )
        if bars:
            idx.latest_close = bars[-1].close
            if len(bars) > 1:
                idx.change = round(bars[-1].close - bars[-2].close, 4)
                idx.change_pct = round((bars[-1].close / bars[-2].close - 1) * 100, 4)
            idx.data_time = utcnow()

    # 4) 宏观
    for m in run_async(mock.get_macro(limit=1000)):
        db.add(
            MacroData(
                indicator=m.indicator,
                value=m.value,
                unit=m.unit,
                period=m.period,
                change=m.change,
                source="mock",
                published_at=m.published_at,
                retrieved_at=utcnow(),
            )
        )

    # 5) 新闻 / 政策
    for n in run_async(mock.get_news(limit=60)):
        db.add(
            News(
                title=n.title,
                content=n.content,
                source=n.source,
                url=n.url,
                published_at=n.published_at,
                related_fund=n.related_fund,
                related_industry=n.related_industry,
                sentiment=n.sentiment,
                importance=n.importance,
                content_hash=_news_hash(n.title, n.source),
                retrieved_at=utcnow(),
            )
        )
    for p in run_async(mock.get_policies(limit=60)):
        db.add(
            Policy(
                title=p.title,
                content=p.content,
                source=p.source,
                url=p.url,
                published_at=p.published_at,
                department=p.department,
                policy_type=p.policy_type,
                related_industry=p.related_industry,
                sentiment=p.sentiment,
                impact_score=p.impact_score,
                importance=p.importance,
                content_hash=_news_hash(p.title, p.source),
                retrieved_at=utcnow(),
            )
        )

    # 6) 演示自选
    for code, group, pinned in DEMO_WATCHLIST:
        if code in fund_ids:
            db.add(Watchlist(user_id=user.id, fund_id=fund_ids[code], group_name=group, pinned=pinned))

    # 7) 欢迎通知
    db.add(
        Notification(
            user_id=user.id,
            title="欢迎使用基金智能分析预测平台",
            content="演示数据已就绪（source=mock）。可在「设置-数据源」中查看数据来源，"
            "连接网络后点击「立即更新」可同步真实基金数据。",
            type="system",
        )
    )
    db.commit()
    log.info("演示数据注入完成：%d 只基金", len(fund_ids))
    return {
        "seeded": True,
        "funds": len(fund_ids),
        "daily_rows": sum(
            db.query(FundDailyData.id).filter(FundDailyData.fund_id == fid).count()
            for fid in fund_ids.values()
        ),
        "demo_user": settings.DEMO_USERNAME,
    }

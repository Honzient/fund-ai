"""基金服务：搜索 / 数据同步（增量）/ 汇总视图 / 历史序列。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func

from app.cache.cache import get_cache
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Fund, FundDailyData, FundHolding
from app.providers import get_registry
from app.providers.base import FundInfo, NavPoint
from app.utils.asyncs import run_async
from app.utils.dates import parse_date, today, utcnow

log = get_logger("app.data")

TIME_RANGE_DAYS = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 1095, "ALL": 3650}

DEFAULT_INDEX_CODES = ["000300", "000905", "000852", "000001", "399006", "NDX", "SPX", "HSI"]


def get_fund_by_code(db, fund_code: str) -> Fund | None:
    return db.query(Fund).filter(Fund.fund_code == fund_code).first()


def _fund_from_info(info: FundInfo) -> Fund:
    return Fund(
        fund_code=info.fund_code,
        fund_name=info.fund_name,
        fund_type=info.fund_type or None,
        manager=info.manager or None,
        company=info.company or None,
        establish_date=info.establish_date,
        benchmark=info.benchmark or None,
        risk_level=info.risk_level or None,
        management_fee=info.management_fee,
        purchase_fee=info.purchase_fee,
        redemption_fee=info.redemption_fee,
        fund_size=info.fund_size,
        latest_nav=info.latest_nav,
        latest_nav_date=info.latest_nav_date,
        source=info.source or "mock",
        retrieved_at=utcnow(),
    )


def ensure_fund(db, fund_code: str) -> Fund | None:
    fund = get_fund_by_code(db, fund_code)
    if fund:
        return fund
    info = run_async(get_registry().call("get_fund_info", fund_code=fund_code))
    if info is None:
        return None
    fund = _fund_from_info(info)
    db.add(fund)
    db.commit()
    db.refresh(fund)
    return fund


def search_funds(keyword: str = "", limit: int = 20) -> list[dict]:
    items = run_async(
        get_registry().call("search_funds", keyword=keyword, limit=limit, default=[])
    )
    out: list[dict] = []
    for item in items:
        out.append(
            {
                "fund_code": item.fund_code,
                "fund_name": item.fund_name,
                "fund_type": item.fund_type,
                "company": item.company,
                "source": item.source,
            }
        )
    return out


def sync_fund_history(db, fund_code: str, years: float = 3.8) -> dict:
    """增量同步净值：只拉取缺失日期区间，合并去重。"""
    fund = ensure_fund(db, fund_code)
    if fund is None:
        return {"status": "failed", "reason": "基金信息获取失败"}
    last: date | None = (
        db.query(func.max(FundDailyData.date)).filter(FundDailyData.fund_id == fund.id).scalar()
    )
    start = last + timedelta(days=1) if last else today() - timedelta(days=int(years * 365))
    if last and (today() - last).days <= 0:
        return {"status": "up_to_date", "latest_date": last.isoformat()}

    points: list[NavPoint] = run_async(
        get_registry().call("get_nav_history", fund_code=fund_code, start=start, default=[])
    )
    if not points:
        # 回退：全量拉取一次（某些数据源不支持区间）
        points = run_async(get_registry().call("get_nav_history", fund_code=fund_code, default=[]))

    existing = {
        row[0]
        for row in db.query(FundDailyData.date).filter(FundDailyData.fund_id == fund.id).all()
    }
    added = 0
    latest_point: NavPoint | None = None
    for p in points:
        if p.date in existing:
            continue
        db.add(
            FundDailyData(
                fund_id=fund.id,
                date=p.date,
                nav=p.nav,
                accumulated_nav=p.accumulated_nav,
                daily_return=p.daily_return,
                volume=p.volume,
                source=p.source or fund.source,
                retrieved_at=utcnow(),
            )
        )
        added += 1
        if latest_point is None or p.date > latest_point.date:
            latest_point = p
    db.commit()
    if added > 0:
        _recompute_returns(db, fund.id)
    if latest_point:
        fund.latest_nav = latest_point.nav
        fund.latest_nav_date = latest_point.date
        fund.updated_at = utcnow()
        db.commit()
    latest_date = (
        db.query(func.max(FundDailyData.date)).filter(FundDailyData.fund_id == fund.id).scalar()
    )
    return {
        "status": "synced" if added > 0 else "up_to_date",
        "new_rows": added,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "source": latest_point.source if latest_point else fund.source,
    }


def _recompute_returns(db, fund_id: int) -> None:
    """补齐缺失的日收益率。"""
    rows = (
        db.query(FundDailyData)
        .filter(FundDailyData.fund_id == fund_id, FundDailyData.daily_return.is_(None))
        .order_by(FundDailyData.date)
        .all()
    )
    if not rows:
        return
    prev = (
        db.query(FundDailyData)
        .filter(FundDailyData.fund_id == fund_id, FundDailyData.date < rows[0].date)
        .order_by(FundDailyData.date.desc())
        .first()
    )
    for row in rows:
        if prev is not None and prev.nav:
            row.daily_return = round(row.nav / prev.nav - 1, 6)
        prev = row
    db.commit()


def history_df(
    db, fund: Fund, start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    q = db.query(FundDailyData).filter(FundDailyData.fund_id == fund.id)
    if start:
        q = q.filter(FundDailyData.date >= start)
    if end:
        q = q.filter(FundDailyData.date <= end)
    rows = q.order_by(FundDailyData.date).all()
    if not rows:
        return pd.DataFrame(columns=["date", "nav", "accumulated_nav", "daily_return", "volume", "source"])
    return pd.DataFrame(
        {
            "date": [r.date for r in rows],
            "nav": [float(r.nav) for r in rows],
            "accumulated_nav": [float(r.accumulated_nav) if r.accumulated_nav else None for r in rows],
            "daily_return": [float(r.daily_return) if r.daily_return is not None else None for r in rows],
            "volume": [float(r.volume) if r.volume else None for r in rows],
            "source": [r.source for r in rows],
        }
    )


def returns_map(db, fund_id: int) -> dict:
    """近1日/5日/20日/60日/1年/年初至今收益（百分比）。"""
    rows = (
        db.query(FundDailyData.date, FundDailyData.nav)
        .filter(FundDailyData.fund_id == fund_id)
        .order_by(FundDailyData.date.desc())
        .all()
    )
    if not rows:
        return {}
    navs = [nav for _, nav in rows]
    dates = [d for d, _ in rows]

    def ret(days: int) -> float | None:
        if len(navs) > days and navs[days]:
            return round((navs[0] / navs[days] - 1) * 100, 4)
        return None

    ytd = None
    year_start = date(today().year, 1, 1)
    for d, nav in zip(dates, navs):
        if d < year_start and nav:
            ytd = round((navs[0] / nav - 1) * 100, 4)
            break
    return {
        "return_1d": ret(1),
        "return_5d": ret(5),
        "return_20d": ret(20),
        "return_60d": ret(60),
        "return_1y": ret(250),
        "return_ytd": ytd,
    }


def _is_trading_session(now: datetime | None = None) -> bool:
    """A股交易时段：周一至周五 09:30–15:00（Asia/Shanghai）。"""
    from datetime import time as dt_time
    from zoneinfo import ZoneInfo

    if now is None:
        from datetime import datetime as dt_mod

        try:
            tz = ZoneInfo(get_settings().TZ)
        except Exception:  # noqa: BLE001
            tz = None
        now = dt_mod.now(tz)
    return now.weekday() < 5 and dt_time(9, 30) <= now.time() <= dt_time(15, 0)


def estimate_for(db, fund_code: str) -> dict | None:
    """盘中估值（仅交易时段请求数据源；负面结果也缓存，避免反复打接口）。"""
    if not _is_trading_session():
        return None
    cache = get_cache()
    key = f"est:{fund_code}"
    cached = cache.get(key)
    if cached is None:
        est = run_async(get_registry().call_first("get_estimate", fund_code=fund_code))
        if est is None:
            # 负面缓存：数据源限流/无估值时，短时间内不再重复请求
            cache.set(key, {"available": False}, ttl=180)
            return None
        cached = {
            "available": True,
            "estimate_nav": float(est.nav),
            "estimate_return": float(est.return_pct),
            "estimate_time": est.time.isoformat() if est.time else None,
            "source": est.source,
        }
        cache.set(key, cached, ttl=300)
    if not cached.get("available"):
        return None
    return {
        "estimate_nav": cached["estimate_nav"],
        "estimate_return": cached["estimate_return"],
        "estimate_time": cached.get("estimate_time"),
        "source": cached.get("source"),
    }


def fund_summary(db, fund: Fund, with_score: bool = False) -> dict:
    """列表视图字段。data_status: latest_available | estimate。"""
    out = {
        "id": fund.id,
        "fund_code": fund.fund_code,
        "fund_name": fund.fund_name,
        "fund_type": fund.fund_type,
        "company": fund.company,
        "latest_nav": fund.latest_nav,
        "latest_nav_date": fund.latest_nav_date.isoformat() if fund.latest_nav_date else None,
        "source": fund.source,
        "retrieved_at": fund.retrieved_at.isoformat() if fund.retrieved_at else None,
        "data_status": "latest_available",
        "risk_level": fund.risk_level,
    }
    rets = returns_map(db, fund.id)
    out.update(rets)
    est = estimate_for(db, fund.fund_code)
    if est:
        out["data_status"] = "estimate"
        out.update(est)
    if with_score:
        from app.services.analysis_service import analyze_fund

        analysis = analyze_fund(db, fund.fund_code, "3M", with_prediction=False)
        out["score"] = analysis.get("score")
    return out


def holdings_payload(db, fund: Fund) -> dict:
    """持仓 + 行业分布 + 集中度。"""
    rows = (
        db.query(FundHolding)
        .filter(FundHolding.fund_id == fund.id)
        .order_by(FundHolding.report_date.desc(), FundHolding.weight.desc())
        .all()
    )
    if not rows:
        return {
            "fund_code": fund.fund_code,
            "report_date": None,
            "top10": [],
            "industry_distribution": [],
            "concentration": {"top10": None, "hhi": None},
            "source": None,
            "retrieved_at": None,
        }
    report_date = rows[0].report_date
    top10 = [r for r in rows if r.report_date == report_date][:10]
    industry_map: dict[str, float] = {}
    for r in top10:
        industry = r.industry or "其他"
        industry_map[industry] = industry_map.get(industry, 0.0) + (r.weight or 0)
    top10_sum = round(sum(r.weight or 0 for r in top10), 2)
    hhi = round(sum((w / 100) ** 2 for w in industry_map.values()), 4) if industry_map else None
    return {
        "fund_code": fund.fund_code,
        "report_date": report_date.isoformat(),
        "top10": [
            {
                "stock_code": r.stock_code,
                "stock_name": r.stock_name,
                "weight": r.weight,
                "industry": r.industry,
                "market_value": r.market_value,
                "source": r.source,
            }
            for r in top10
        ],
        "industry_distribution": [
            {"industry": k, "weight": round(v, 2)} for k, v in sorted(industry_map.items(), key=lambda kv: -kv[1])
        ],
        "concentration": {"top10": top10_sum, "hhi": hhi},
        "source": top10[0].source if top10 else None,
        "retrieved_at": top10[0].retrieved_at.isoformat() if top10[0].retrieved_at else None,
    }


def sync_holdings(db, fund_code: str) -> dict:
    fund = ensure_fund(db, fund_code)
    if fund is None:
        return {"status": "failed"}
    items = run_async(get_registry().call("get_holdings", fund_code=fund_code, default=[]))
    if not items:
        return {"status": "no_data"}
    report_date = items[0].report_date
    existing = {
        row[0]
        for row in db.query(FundHolding.stock_code).filter(
            FundHolding.fund_id == fund.id, FundHolding.report_date == report_date
        ).all()
    }
    from app.models import industry_of

    added = 0
    for item in items:
        if item.stock_code in existing:
            continue
        # 行业解析：优先行业分类表（SecurityIndustry），其次 Provider 提示，最后 unknown
        industry = item.industry
        if not industry or industry in ("unknown", "其他"):
            industry = industry_of(db, item.stock_code)
        if not industry or industry in ("其他",):
            industry = "unknown"
        db.add(
            FundHolding(
                fund_id=fund.id,
                report_date=item.report_date,
                stock_code=item.stock_code,
                stock_name=item.stock_name,
                weight=item.weight,
                industry=industry,
                market_value=item.market_value,
                source=item.source,
                retrieved_at=utcnow(),
            )
        )
        added += 1
    db.commit()
    return {"status": "synced", "new_rows": added, "report_date": report_date.isoformat()}


def all_fund_codes(db) -> list[str]:
    return [row[0] for row in db.query(Fund.fund_code).order_by(Fund.id).all()]

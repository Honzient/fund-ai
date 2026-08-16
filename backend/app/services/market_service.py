"""市场指数服务：同步 / 历史 / 市场概况 / 市场状态。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func

from app.core.logging import get_logger
from app.models import MarketIndex, MarketIndexData
from app.providers import get_registry
from app.providers.base import IndexBar
from app.utils.asyncs import run_async
from app.utils.dates import today, utcnow

log = get_logger("app.data")

DEFAULT_INDEXES: list[tuple[str, str, str]] = [
    ("000300", "沪深300", "CN"),
    ("000905", "中证500", "CN"),
    ("000852", "中证1000", "CN"),
    ("000001", "上证指数", "CN"),
    ("399006", "创业板指", "CN"),
    ("NDX", "纳斯达克100", "US"),
    ("SPX", "标普500", "US"),
    ("HSI", "恒生指数", "HK"),
]


def ensure_indexes(db) -> list[MarketIndex]:
    existing = {i.index_code: i for i in db.query(MarketIndex).all()}
    for code, name, market in DEFAULT_INDEXES:
        if code not in existing:
            idx = MarketIndex(index_code=code, index_name=name, market=market, source="mock")
            db.add(idx)
            existing[code] = idx
    db.commit()
    return list(existing.values())


def sync_index_history(db, index_code: str, years: float = 3.8) -> dict:
    idx = db.query(MarketIndex).filter(MarketIndex.index_code == index_code).first()
    if idx is None:
        ensure_indexes(db)
        idx = db.query(MarketIndex).filter(MarketIndex.index_code == index_code).first()
        if idx is None:
            return {"status": "failed", "reason": "未知指数"}
    last: date | None = (
        db.query(func.max(MarketIndexData.date))
        .filter(MarketIndexData.index_id == idx.id)
        .scalar()
    )
    start = last + timedelta(days=1) if last else today() - timedelta(days=int(years * 365))
    if last and (today() - last).days <= 0:
        return {"status": "up_to_date", "latest_date": last.isoformat()}

    bars: list[IndexBar] = run_async(
        get_registry().call("get_index_history", index_code=index_code, start=start, default=[])
    )
    if not bars:
        bars = run_async(get_registry().call("get_index_history", index_code=index_code, default=[]))
    existing = {
        row[0]
        for row in db.query(MarketIndexData.date).filter(MarketIndexData.index_id == idx.id).all()
    }
    added = 0
    latest_bar: IndexBar | None = None
    for bar in bars:
        if bar.date in existing:
            continue
        db.add(
            MarketIndexData(
                index_id=idx.id,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                source=bar.source or idx.source,
                retrieved_at=utcnow(),
            )
        )
        added += 1
        if latest_bar is None or bar.date > latest_bar.date:
            latest_bar = bar
    if latest_bar:
        prev_close = (
            db.query(MarketIndexData.close)
            .filter(MarketIndexData.index_id == idx.id, MarketIndexData.date < latest_bar.date)
            .order_by(MarketIndexData.date.desc())
            .first()
        )
        idx.latest_close = latest_bar.close
        if prev_close and prev_close[0]:
            idx.change = round(latest_bar.close - prev_close[0], 4)
            idx.change_pct = round((latest_bar.close / prev_close[0] - 1) * 100, 4)
        idx.data_time = utcnow()
        idx.source = latest_bar.source or idx.source
        idx.retrieved_at = utcnow()
    db.commit()
    latest_date = (
        db.query(func.max(MarketIndexData.date))
        .filter(MarketIndexData.index_id == idx.id)
        .scalar()
    )
    return {
        "status": "synced" if added > 0 else "up_to_date",
        "new_rows": added,
        "latest_date": latest_date.isoformat() if latest_date else None,
    }


def index_summary(db, idx: MarketIndex) -> dict:
    return {
        "id": idx.id,
        "index_code": idx.index_code,
        "index_name": idx.index_name,
        "market": idx.market,
        "latest_close": idx.latest_close,
        "change": idx.change,
        "change_pct": idx.change_pct,
        "data_time": idx.data_time.isoformat() if idx.data_time else None,
        "source": idx.source,
        "data_status": "latest_available",
    }


def index_history_df(
    db, index_code: str, start: date | None = None, end: date | None = None
) -> tuple[MarketIndex | None, pd.DataFrame]:
    idx = db.query(MarketIndex).filter(MarketIndex.index_code == index_code).first()
    if idx is None:
        return None, pd.DataFrame()
    q = db.query(MarketIndexData).filter(MarketIndexData.index_id == idx.id)
    if start:
        q = q.filter(MarketIndexData.date >= start)
    if end:
        q = q.filter(MarketIndexData.date <= end)
    rows = q.order_by(MarketIndexData.date).all()
    if not rows:
        return idx, pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return idx, pd.DataFrame(
        {
            "date": [r.date for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [float(r.volume) if r.volume else None for r in rows],
        }
    )


def benchmark_close_series(db) -> pd.Series | None:
    """默认基准（沪深300）收盘价序列，日期索引。"""
    idx = db.query(MarketIndex).filter(MarketIndex.index_code == "000300").first()
    if idx is None:
        return None
    rows = (
        db.query(MarketIndexData.date, MarketIndexData.close)
        .filter(MarketIndexData.index_id == idx.id)
        .order_by(MarketIndexData.date)
        .all()
    )
    if not rows:
        return None
    return pd.Series(
        [float(c) for _, c in rows],
        index=pd.Index([d for d, _ in rows], name="date"),
    )


def market_overview(db) -> dict:
    """市场概况：指数快照 + 市场状态（中性偏多/中性/中性偏空 + 驱动因素）。"""
    ensure_indexes(db)
    indexes = [index_summary(db, i) for i in db.query(MarketIndex).order_by(MarketIndex.id).all()]
    cn = [i for i in indexes if i["market"] == "CN" and i["change_pct"] is not None]
    breadth = round(sum(1 for i in cn if i["change_pct"] > 0) / len(cn) * 100, 1) if cn else 50.0
    avg_change = round(sum(i["change_pct"] for i in cn) / len(cn), 2) if cn else 0.0

    # 20日动量（基于沪深300）
    benchmark = benchmark_close_series(db)
    mom20 = None
    if benchmark is not None and len(benchmark) > 20:
        mom20 = float(benchmark.iloc[-1] / benchmark.iloc[-21] - 1)
    score = 50.0 + (mom20 or 0) * 400 + (breadth - 50) * 0.3
    score = max(0.0, min(100.0, score))
    label = "中性偏多" if score >= 60 else ("中性偏空" if score <= 40 else "中性")
    drivers: list[str] = []
    if mom20 is not None:
        drivers.append(f"沪深300近20日 {'上涨' if mom20 > 0 else '下跌'} {abs(mom20) * 100:.1f}%")
    drivers.append(f"A股指数上涨广度 {breadth:.0f}%")
    if avg_change > 0.5:
        drivers.append("主要指数今日普涨，风险偏好回升")
    elif avg_change < -0.5:
        drivers.append("主要指数今日普跌，风险偏好回落")
    return {
        "indices": indexes,
        "market_regime": {"label": label, "score": round(score, 1), "drivers": drivers},
        "breadth": breadth,
        "generated_at": today().isoformat(),
    }

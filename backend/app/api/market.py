"""市场接口：指数列表 / 历史 / 市场概况 / 同步。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services import market_service, sync_service
from app.tasks import get_task_manager
from app.utils.dates import parse_date

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/indexes")
def list_indexes(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    market_service.ensure_indexes(db)
    indexes = db.query(market_service.MarketIndex).order_by(market_service.MarketIndex.id).all()
    return [market_service.index_summary(db, i) for i in indexes]


@router.get("/indexes/{index_code}/history")
def index_history(
    index_code: str,
    start: str | None = None,
    end: str | None = None,
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    idx, df = market_service.index_history_df(db, index_code, parse_date(start), parse_date(end))
    if idx is None:
        raise HTTPException(status_code=404, detail="未知指数")
    if df.empty:
        market_service.sync_index_history(db, index_code)
        idx, df = market_service.index_history_df(db, index_code, parse_date(start), parse_date(end))
    if df.empty:
        return {
            "index": {"index_code": idx.index_code, "index_name": idx.index_name},
            "items": [],
            "count": 0,
            "data_status": "latest_available",
        }
    df = df.sort_values("date")
    if period != "daily":
        df = (
            df.set_index("date")
            .resample("W" if period == "weekly" else "ME")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["close"])
            .reset_index()
        )
    items = []
    prev_close = None
    for row in df.itertuples(index=False):
        change_pct = (
            round((float(row.close) / prev_close - 1) * 100, 4) if prev_close else None
        )
        items.append(
            {
                "date": row.date.isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume) if row.volume is not None else None,
                "change_pct": change_pct,
            }
        )
        prev_close = float(row.close)
    return {
        "index": {"index_code": idx.index_code, "index_name": idx.index_name},
        "items": items,
        "count": len(items),
        "period": period,
        "data_status": "latest_available",
    }


@router.get("/overview")
def market_overview(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return market_service.market_overview(db)


@router.post("/sync")
def sync_market(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    result = get_task_manager().run("sync.market", lambda: sync_service.sync_market(), retries=1)
    return {"task_id": result["task_id"], "status": "started"}

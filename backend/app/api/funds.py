"""基金接口：搜索 / 详情 / 历史 / 持仓 / 指标 / 风险 / 分析 / 预测 / 同步。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics.indicators import compute_all, indicator_series, latest_indicators
from app.analytics.relative import compute_relative
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services import analysis_service, fund_service, market_service, news_service
from app.tasks import get_task_manager
from app.utils.dates import parse_date, today

router = APIRouter(prefix="/funds", tags=["funds"])


@router.get("")
def list_funds(
    search: str = "",
    fund_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if search:
        items = fund_service.search_funds(search, limit=20)
        codes = [i["fund_code"] for i in items]
        funds = [
            fund_service.get_fund_by_code(db, code) or fund_service.ensure_fund(db, code)
            for code in codes
        ]
        funds = [f for f in funds if f is not None]
    else:
        from app.models import Fund

        q = db.query(Fund)
        if fund_type:
            q = q.filter(Fund.fund_type.like(f"%{fund_type}%"))
        funds = q.order_by(Fund.id).limit(limit).all()
    return [fund_service.fund_summary(db, f, with_score=False) for f in funds]


@router.get("/{fund_code}")
def fund_detail(
    fund_code: str,
    with_prediction: bool = Query(default=True),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在或数据源无法获取")
    summary = fund_service.fund_summary(db, fund, with_score=False)
    analysis = analysis_service.analyze_fund(db, fund_code, "3M", with_prediction=with_prediction)
    summary.update(
        {
            "manager": fund.manager,
            "establish_date": fund.establish_date.isoformat() if fund.establish_date else None,
            "benchmark": fund.benchmark,
            "fund_size": fund.fund_size,
            "fees": {
                "management_fee": fund.management_fee,
                "purchase_fee": fund.purchase_fee,
                "redemption_fee": fund.redemption_fee,
            },
            "ai_score": analysis["score"],
            "trend": analysis["trend"],
            "score_breakdown": analysis["score_breakdown"],
            "predictions": analysis.get("predictions"),
            "data_time": analysis.get("data_time"),
            "data_as_of": analysis.get("data_as_of"),
        }
    )
    return summary


@router.get("/{fund_code}/history")
def fund_history(
    fund_code: str,
    start: str | None = None,
    end: str | None = None,
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    df = fund_service.history_df(db, fund, parse_date(start), parse_date(end))
    if len(df) < 30:
        fund_service.sync_fund_history(db, fund_code)
        df = fund_service.history_df(db, fund, parse_date(start), parse_date(end))
    if df.empty:
        return {
            "fund": {"fund_code": fund_code, "fund_name": fund.fund_name},
            "items": [],
            "count": 0,
            "period": period,
            "data_status": "latest_available",
        }
    df = df.sort_values("date")
    if period != "daily":
        df = df.set_index("date").resample("W" if period == "weekly" else "ME").last().dropna(subset=["nav"]).reset_index()
    items = [
        {
            "date": row.date.isoformat(),
            "nav": float(row.nav),
            "accumulated_nav": float(row.accumulated_nav) if row.accumulated_nav else None,
            "daily_return": (
                float(row.daily_return) if row.daily_return is not None and pd.notna(row.daily_return) else None
            ),
            "volume": float(row.volume) if row.volume and pd.notna(row.volume) else None,
            "source": row.source,
        }
        for row in df.itertuples(index=False)
    ]
    return {
        "fund": {"fund_code": fund_code, "fund_name": fund.fund_name},
        "items": items,
        "count": len(items),
        "period": period,
        "data_status": "latest_available",
    }


@router.get("/{fund_code}/holdings")
def fund_holdings(
    fund_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    payload = fund_service.holdings_payload(db, fund)
    if not payload["top10"]:
        fund_service.sync_holdings(db, fund_code)
        payload = fund_service.holdings_payload(db, fund)
    return payload


@router.get("/{fund_code}/indicators")
def fund_indicators(
    fund_code: str,
    limit: int = Query(default=400, ge=30, le=1200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    df = fund_service.history_df(db, fund)
    if len(df) < 30:
        fund_service.sync_fund_history(db, fund_code)
        df = fund_service.history_df(db, fund)
    if df.empty:
        raise HTTPException(status_code=404, detail="无历史数据")
    computed = compute_all(df)
    return {
        "fund_code": fund_code,
        "date": df["date"].iloc[-1].isoformat(),
        "computed_at": today().isoformat(),
        "indicators": latest_indicators(computed),
        "series": indicator_series(computed, limit=limit),
    }


@router.get("/{fund_code}/risk")
def fund_risk(
    fund_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    analysis = analysis_service.analyze_fund(db, fund_code, "1Y", with_prediction=False)
    return {
        "fund_code": fund_code,
        "period": "1Y",
        "computed_at": analysis["computed_at"],
        "metrics": analysis["risk"],
    }


@router.get("/{fund_code}/analysis")
def fund_analysis(
    fund_code: str,
    time_range: str = Query(default="3M", pattern="^(1M|3M|6M|1Y|3Y)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return analysis_service.analyze_fund(db, fund_code, time_range, with_prediction=True)


@router.get("/{fund_code}/prediction")
def fund_prediction(
    fund_code: str,
    horizon: str = Query(default="short", pattern="^(short|medium|long)$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    analysis = analysis_service.analyze_fund(db, fund_code, "3M", with_prediction=True)
    return analysis["predictions"][horizon]


@router.get("/{fund_code}/relative")
def fund_relative(
    fund_code: str,
    benchmark: str = Query(default="000300"),
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """基金 vs 基准：超额收益 / 相对强弱 / Beta / Alpha。"""
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    s = parse_date(start) or today() - timedelta(days=365)
    e = parse_date(end) or today()
    fund_df = fund_service.history_df(db, fund, s, e)
    idx, bench_df = market_service.index_history_df(db, benchmark, s, e)
    if fund_df.empty or bench_df.empty:
        raise HTTPException(status_code=404, detail="数据不足，无法对比")
    result = compute_relative(fund_df, bench_df)
    return {
        "fund_code": fund_code,
        "benchmark": benchmark,
        "benchmark_name": idx.index_name if idx else benchmark,
        **result,
    }


@router.post("/{fund_code}/sync")
def sync_fund(
    fund_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """手动触发单只基金数据同步。"""
    fund_service.ensure_fund(db, fund_code)

    def _work():
        return fund_service.sync_fund_full(fund_code)

    result = get_task_manager().run(f"sync.fund.{fund_code}", _work, retries=1)
    return {"task_id": result["task_id"], "status": "started"}


@router.get("/{fund_code}/news")
def fund_news(
    fund_code: str,
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    return {"fund_code": fund_code, "items": news_service.news_for_fund(db, fund, limit=limit)}


@router.get("/{fund_code}/policies")
def fund_policies(
    fund_code: str,
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    return {"fund_code": fund_code, "items": news_service.policies_for_fund(db, fund, limit=limit)}

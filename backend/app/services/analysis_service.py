"""分析服务：组装因子上下文 → 多因子评分 → 预测 → 可解释输出。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.analytics.factors import FactorContext, compute_factor_scores
from app.analytics.indicators import compute_all, latest_indicators
from app.analytics.risk import compute_risk_metrics
from app.cache.cache import get_cache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import AnalysisSnapshot, Fund, FundHolding, MacroData
from app.prediction import PredictionEngine
from app.services import fund_service, market_service, news_service
from app.utils.dates import parse_date, today, utcnow

log = get_logger("app.analysis")

_engine: PredictionEngine | None = None


def get_engine() -> PredictionEngine:
    global _engine
    if _engine is None:
        _engine = PredictionEngine()
    return _engine


def _macro_latest(db) -> dict[str, float]:
    rows = db.query(MacroData).order_by(MacroData.period.desc()).all()
    latest: dict[str, float] = {}
    for row in rows:
        if row.indicator not in latest:
            latest[row.indicator] = float(row.value)
    return latest


def _industry_weights(db, fund: Fund) -> dict[str, float]:
    rows = (
        db.query(FundHolding)
        .filter(FundHolding.fund_id == fund.id)
        .order_by(FundHolding.report_date.desc())
        .all()
    )
    if not rows:
        return {}
    report_date = rows[0].report_date
    weights: dict[str, float] = {}
    for r in rows:
        if r.report_date != report_date:
            continue
        industry = r.industry or "其他"
        weights[industry] = weights.get(industry, 0.0) + (r.weight or 0)
    return weights


def build_factor_context(db, fund: Fund, df: pd.DataFrame, time_range: str = "3M") -> FactorContext:
    """组装 7 维因子所需全部输入。"""
    days = fund_service.TIME_RANGE_DAYS.get(time_range, 91)
    start = today() - timedelta(days=days)
    window_df = df[df["date"] >= start]
    nav_series = (
        window_df.set_index("date")["nav"] if not window_df.empty else df.set_index("date")["nav"]
    )
    benchmark = market_service.benchmark_close_series(db)
    bench_returns = None
    if benchmark is not None and not window_df.empty:
        bench_window = benchmark[benchmark.index >= window_df["date"].min()]
        bench_returns = bench_window.pct_change().dropna()
    risk_metrics = compute_risk_metrics(nav_series, bench_returns)

    industries = _industry_weights(db, fund)
    holdings_rows = (
        db.query(FundHolding)
        .filter(FundHolding.fund_id == fund.id)
        .order_by(FundHolding.report_date.desc(), FundHolding.weight.desc())
        .all()
    )
    top10_sum = 0.0
    if holdings_rows:
        report_date = holdings_rows[0].report_date
        top10 = [r for r in holdings_rows if r.report_date == report_date][:10]
        top10_sum = round(sum(r.weight or 0 for r in top10), 2)

    age_years = 0.0
    if fund.establish_date:
        age_years = max(0.0, (today() - fund.establish_date).days / 365.25)

    industry_list = list(industries.keys())
    agg = news_service.aggregate_sentiment(db, industries=industry_list)

    # 市场环境：20/60日动量 + RSI（用全量指数数据）
    market_20d = market_60d = 0.0
    market_rsi = None
    if benchmark is not None and len(benchmark) > 60:
        market_20d = float(benchmark.iloc[-1] / benchmark.iloc[-21] - 1)
        market_60d = float(benchmark.iloc[-1] / benchmark.iloc[-61] - 1)
        from app.analytics.indicators import rsi as rsi_fn

        rsi_v = rsi_fn(benchmark, 14)
        if not rsi_v.empty and pd.notna(rsi_v.iloc[-1]):
            market_rsi = float(rsi_v.iloc[-1])

    return FactorContext(
        df=df,
        risk_metrics=risk_metrics,
        fund_age_years=age_years,
        fund_size=fund.fund_size,
        holdings_industries=industries,
        top10_weight=top10_sum,
        macro_latest=_macro_latest(db),
        news_avg_sentiment=agg["news"]["avg_sentiment"],
        news_industry_sentiment=agg["news"]["industry_sentiment"],
        policy_avg_impact=agg["policies"]["avg_sentiment"],
        policy_industry_impact=agg["policies"]["industry_sentiment"],
        market_20d_return=market_20d,
        market_60d_return=market_60d,
        market_rsi=market_rsi,
    )


def _save_snapshot(db, fund: Fund, horizon: str, prediction: dict) -> None:
    try:
        probs = prediction.get("probabilities", {})
        db.add(
            AnalysisSnapshot(
                fund_id=fund.id,
                model_version=prediction.get("model_version", "baseline"),
                horizon=horizon,
                horizon_days=prediction.get("horizon_days", 5),
                prob_up=probs.get("up", 0.0),
                prob_range=probs.get("range", 0.0),
                prob_down=probs.get("down", 0.0),
                score=prediction.get("score"),
                confidence=prediction.get("confidence", "low"),
                factors_json=prediction.get("factors"),
                data_as_of=parse_date(prediction.get("data_as_of")),
            )
        )
        db.commit()
        # 清理 60 天前的旧快照，控制体积
        cutoff = utcnow() - timedelta(days=60)
        db.query(AnalysisSnapshot).filter(
            AnalysisSnapshot.fund_id == fund.id, AnalysisSnapshot.created_at < cutoff
        ).delete()
        db.commit()
    except Exception as exc:  # noqa: BLE001 快照失败不影响主流程
        log.warning("预测快照保存失败: %s", exc)


def analyze_fund(db, fund_code: str, time_range: str = "3M", with_prediction: bool = True) -> dict:
    """基金完整分析。结果缓存（10分钟），保证列表页/详情页性能。"""
    settings = get_settings()
    cache = get_cache()
    cache_key = f"analysis:{fund_code}:{time_range}:{int(with_prediction)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    fund = fund_service.ensure_fund(db, fund_code)
    if fund is None:
        raise ValueError(f"基金 {fund_code} 不存在或数据源无法获取")
    df = fund_service.history_df(db, fund)
    if len(df) < 60:
        sync_result = fund_service.sync_fund_history(db, fund_code)
        log.info("历史数据不足(%d)，触发同步: %s", len(df), sync_result)
        df = fund_service.history_df(db, fund)
    if len(df) < 30:
        raise ValueError("基金历史数据不足（<30 条），无法分析")

    computed_df = compute_all(df)
    indicators = latest_indicators(computed_df)
    ctx = build_factor_context(db, fund, df, time_range)
    factor_result = compute_factor_scores(ctx)

    data_sources = [
        {
            "name": "基金净值历史",
            "source": fund.source,
            "retrieved_at": fund.retrieved_at.isoformat() if fund.retrieved_at else None,
        },
        {"name": "市场指数", "source": "eastmoney/mock", "retrieved_at": today().isoformat()},
    ]
    result = {
        "fund": {
            "fund_code": fund.fund_code,
            "fund_name": fund.fund_name,
            "fund_type": fund.fund_type,
            "company": fund.company,
        },
        "time_range": time_range,
        "computed_at": utcnow().isoformat(),
        "data_as_of": df["date"].iloc[-1].isoformat() if not df.empty else None,
        "score": factor_result["score"],
        "score_breakdown": factor_result["score_breakdown"],
        "trend": factor_result["trend"],
        "positive_factors": factor_result["positive_factors"],
        "negative_factors": factor_result["negative_factors"],
        "main_risks": factor_result["main_risks"],
        "indicators": indicators,
        "risk": ctx.risk_metrics,
        "holdings": fund_service.holdings_payload(db, fund),
        "data_sources": data_sources,
        "data_status": "latest_available",
        "data_time": fund.latest_nav_date.isoformat() if fund.latest_nav_date else None,
    }

    if with_prediction:
        predictions = {}
        engine = get_engine()
        for horizon in ("short", "medium", "long"):
            pred = engine.predict(fund_code, horizon)
            pred["factors"] = {
                "positive": factor_result["positive_factors"],
                "negative": factor_result["negative_factors"],
                "risks": factor_result["main_risks"],
            }
            pred["score"] = factor_result["score"]
            predictions[horizon] = pred
            _save_snapshot(db, fund, horizon, pred)
        result["predictions"] = predictions
        # 删除旧缓存键策略：重新设置
    cache.set(cache_key, result, ttl=settings.ANALYSIS_CACHE_TTL)
    return result


def compare_funds(db, fund_codes: list[str], time_range: str = "3M") -> dict:
    """多基金对比。"""
    analyses = [analyze_fund(db, code, time_range, with_prediction=True) for code in fund_codes]
    table: list[dict] = []
    for a in analyses:
        risk = a.get("risk", {})
        fund = a["fund"]
        table.append(
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "score": a["score"],
                "sharpe": risk.get("sharpe"),
                "max_drawdown": risk.get("max_drawdown"),
                "annual_volatility": risk.get("annual_volatility"),
                "return_1m": _period_return(a),
                "trend_short": a["trend"]["short"],
                "trend_medium": a["trend"]["medium"],
                "trend_long": a["trend"]["long"],
                "prob_up_short": a["predictions"]["short"]["probabilities"]["up"],
                "confidence_short": a["predictions"]["short"]["confidence"],
            }
        )
    by_score = sorted(table, key=lambda r: -(r["score"] or 0))
    by_risk = sorted(table, key=lambda r: (r["max_drawdown"] is None, -(r["max_drawdown"] or 0)))
    return {
        "generated_at": utcnow().isoformat(),
        "time_range": time_range,
        "funds": analyses,
        "comparison": {
            "table": table,
            "highest_score": by_score[0]["fund_code"] if by_score else None,
            "best_trend": by_score[0]["fund_code"] if by_score else None,
            "lowest_risk": by_risk[0]["fund_code"] if by_risk else None,
        },
        "market": market_service.market_overview(db),
    }


def _period_return(analysis: dict) -> float | None:
    """分析窗口内的区间收益。"""
    code = analysis["fund"]["fund_code"]
    db = SessionLocal()
    try:
        fund = fund_service.get_fund_by_code(db, code)
        if fund is None:
            return None
        df = fund_service.history_df(db, fund)
        if df is None or len(df) < 2:
            return None
        days = fund_service.TIME_RANGE_DAYS.get(analysis.get("time_range", "3M"), 91)
        start = today() - timedelta(days=days)
        window = df[df["date"] >= start]
        if window.empty:
            window = df
        return round((float(window["nav"].iloc[-1]) / float(window["nav"].iloc[0]) - 1) * 100, 2)
    finally:
        db.close()

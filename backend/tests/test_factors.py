"""多因子评分与预测特征测试。"""
import numpy as np
import pandas as pd
import pytest

from app.analytics.factors import FactorContext, compute_factor_scores
from app.prediction.features import FEATURE_COLUMNS, add_features


def _context(nav: pd.Series) -> FactorContext:
    dates = pd.bdate_range("2024-01-01", periods=len(nav))
    return FactorContext(
        df=pd.DataFrame({"date": dates, "nav": nav.values}),
        risk_metrics={"max_drawdown": -15.0, "sharpe": 0.8, "sortino": 1.0, "cvar_95": 2.0},
        fund_age_years=10,
        fund_size=100,
        holdings_industries={"食品饮料": 40, "医药生物": 30},
        top10_weight=55,
        macro_latest={"制造业PMI": 50.8, "CPI同比": 2.0, "M2同比": 8.5, "1年期LPR": 3.2, "美元兑人民币": 7.15},
        news_avg_sentiment=0.2,
        news_industry_sentiment={"食品饮料": 0.3},
        policy_avg_impact=0.1,
        policy_industry_impact={"食品饮料": 0.2},
        market_20d_return=0.01,
        market_60d_return=0.02,
        market_rsi=55,
    )


def test_composite_in_range_and_structure():
    rng = np.random.default_rng(11)
    nav = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 400))))
    result = compute_factor_scores(_context(nav))
    assert 0 <= result["score"] <= 100
    assert set(result["score_breakdown"].keys()) == {
        "trend", "volatility", "risk", "quality", "macro", "industry", "sentiment"
    }
    assert set(result["trend"].keys()) == {"short", "medium", "long"}
    assert all(0 <= v <= 100 for v in result["score_breakdown"].values())
    for item in result["positive_factors"] + result["negative_factors"]:
        assert item["factor"] and item["reason"] and isinstance(item["value"], float)
    for risk in result["main_risks"]:
        assert risk["category"] and risk["detail"] and risk["severity"] in ("low", "medium", "high")


def test_uptrend_scores_higher_than_downtrend():
    rng = np.random.default_rng(12)
    base = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 400)))
    up = pd.Series(base * np.linspace(1, 1.8, 400))
    down = pd.Series(base * np.linspace(1.8, 0.55, 400))
    up_score = compute_factor_scores(_context(up))
    down_score = compute_factor_scores(_context(down))
    assert up_score["trend"]["short"] in ("偏多", "中性")
    assert down_score["trend"]["short"] in ("偏空", "中性")
    assert up_score["score"] > down_score["score"]


def test_features_no_future_leakage():
    """特征在 t 时刻只依赖 t 及以前数据：修改尾部不影响历史特征。"""
    rng = np.random.default_rng(13)
    dates = pd.bdate_range("2023-01-01", periods=400)
    nav = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 400))))
    market = pd.Series(
        3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 400))),
        index=pd.Index(dates, name="date"),
    )
    df1 = pd.DataFrame({"date": dates, "nav": nav.values})
    feats1 = add_features(df1, market)
    # 篡改最近 8 天的净值（未来信息）
    nav2 = nav.copy()
    nav2.iloc[-8:] = nav2.iloc[-8:] * 1.5
    feats2 = add_features(pd.DataFrame({"date": dates, "nav": nav2.values}), market)
    # 距尾部足够远的行（不受 rolling 窗口影响）特征应完全一致
    cutoff = len(dates) - 80
    for col in FEATURE_COLUMNS:
        a = feats1[col].iloc[:cutoff].reset_index(drop=True)
        b = feats2[col].iloc[:cutoff].reset_index(drop=True)
        assert np.allclose(a.fillna(0), b.fillna(0), atol=1e-12), f"特征 {col} 出现未来数据泄露"


def test_features_all_columns_present():
    rng = np.random.default_rng(14)
    dates = pd.bdate_range("2023-01-01", periods=300)
    nav = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 300))))
    feats = add_features(pd.DataFrame({"date": dates, "nav": nav.values}), None)
    assert all(col in feats.columns for col in FEATURE_COLUMNS)

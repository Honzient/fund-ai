"""风险指标计算（纯函数）。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def annual_return(daily_returns: pd.Series) -> float:
    """年化收益（几何）。"""
    if len(daily_returns) < 2:
        return 0.0
    total = (1 + daily_returns.fillna(0)).prod()
    years = len(daily_returns) / TRADING_DAYS
    if years <= 0:
        return 0.0
    return float(total ** (1 / years) - 1) if total > 0 else -1.0


def annual_volatility(daily_returns: pd.Series) -> float:
    if len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std(ddof=1) * math.sqrt(TRADING_DAYS))


def downside_volatility(daily_returns: pd.Series, threshold: float = 0.0) -> float:
    downside = daily_returns[daily_returns < threshold]
    if len(downside) < 2:
        return 0.0
    return float(downside.std(ddof=1) * math.sqrt(TRADING_DAYS))


def max_drawdown(series: pd.Series) -> float:
    """最大回撤（负值，-0.25 = 25% 回撤）。series 为净值序列。"""
    if len(series) < 2:
        return 0.0
    roll_max = series.cummax()
    drawdown = series / roll_max - 1
    return float(drawdown.min())


def drawdown_series(series: pd.Series) -> pd.Series:
    roll_max = series.cummax()
    return series / roll_max - 1


def sharpe_ratio(daily_returns: pd.Series, rf_annual: float = 0.02) -> float:
    vol = annual_volatility(daily_returns)
    if vol == 0:
        return 0.0
    excess = daily_returns.mean() * TRADING_DAYS - rf_annual
    return float(excess / vol)


def sortino_ratio(daily_returns: pd.Series, rf_annual: float = 0.02) -> float:
    dvol = downside_volatility(daily_returns)
    if dvol == 0:
        return 0.0
    excess = daily_returns.mean() * TRADING_DAYS - rf_annual
    return float(excess / dvol)


def calmar_ratio(daily_returns: pd.Series, nav_series: pd.Series) -> float:
    ann = annual_return(daily_returns)
    mdd = max_drawdown(nav_series)
    if mdd == 0:
        return 0.0
    return float(ann / abs(mdd))


def var_95(daily_returns: pd.Series) -> float:
    """历史法 95% VaR（日度，正值表示损失）。"""
    if len(daily_returns) < 20:
        return 0.0
    return float(-np.percentile(daily_returns.dropna(), 5))


def cvar_95(daily_returns: pd.Series) -> float:
    """历史法 95% CVaR（期望损失）。"""
    if len(daily_returns) < 20:
        return 0.0
    tail = daily_returns.dropna()[daily_returns <= np.percentile(daily_returns, 5)]
    return float(-tail.mean())


def beta_alpha(
    daily_returns: pd.Series, benchmark_returns: pd.Series, rf_annual: float = 0.02
) -> tuple[float, float]:
    """Beta / 年化 Alpha。序列需按日期对齐。"""
    df = pd.DataFrame({"r": daily_returns, "b": benchmark_returns}).dropna()
    if len(df) < 20 or df["b"].std() == 0:
        return 0.0, 0.0
    cov = df["r"].cov(df["b"])
    var = df["b"].var()
    beta = float(cov / var)
    rf_daily = rf_annual / TRADING_DAYS
    alpha_daily = df["r"].mean() - rf_daily - beta * (df["b"].mean() - rf_daily)
    alpha = float((1 + alpha_daily) ** TRADING_DAYS - 1)
    return beta, alpha


def tracking_error(daily_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    df = pd.DataFrame({"r": daily_returns, "b": benchmark_returns}).dropna()
    if len(df) < 2:
        return 0.0
    diff = df["r"] - df["b"]
    return float(diff.std(ddof=1) * math.sqrt(TRADING_DAYS))


def information_ratio(daily_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    df = pd.DataFrame({"r": daily_returns, "b": benchmark_returns}).dropna()
    if len(df) < 2:
        return 0.0
    diff = df["r"] - df["b"]
    te = diff.std(ddof=1) * math.sqrt(TRADING_DAYS)
    if te == 0:
        return 0.0
    return float(diff.mean() * TRADING_DAYS / te)


def compute_risk_metrics(
    nav_series: pd.Series,
    benchmark_returns: pd.Series | None = None,
    rf_annual: float = 0.02,
) -> dict:
    """从净值序列计算全部风险指标。"""
    nav_series = nav_series.dropna()
    if len(nav_series) < 2:
        return {}
    daily_returns = nav_series.pct_change().dropna()
    metrics: dict = {
        "annual_return": round(annual_return(daily_returns) * 100, 4),
        "annual_volatility": round(annual_volatility(daily_returns) * 100, 4),
        "downside_volatility": round(downside_volatility(daily_returns) * 100, 4),
        "max_drawdown": round(max_drawdown(nav_series) * 100, 4),
        "sharpe": round(sharpe_ratio(daily_returns, rf_annual), 4),
        "sortino": round(sortino_ratio(daily_returns, rf_annual), 4),
        "calmar": round(calmar_ratio(daily_returns, nav_series), 4),
        "var_95": round(var_95(daily_returns) * 100, 4),
        "cvar_95": round(cvar_95(daily_returns) * 100, 4),
        "best_day": round(float(daily_returns.max()) * 100, 4),
        "worst_day": round(float(daily_returns.min()) * 100, 4),
    }
    if benchmark_returns is not None and len(benchmark_returns) > 20:
        beta, alpha = beta_alpha(daily_returns, benchmark_returns, rf_annual)
        metrics["beta"] = round(beta, 4)
        metrics["alpha"] = round(alpha * 100, 4)
        metrics["tracking_error"] = round(tracking_error(daily_returns, benchmark_returns) * 100, 4)
        metrics["information_ratio"] = round(information_ratio(daily_returns, benchmark_returns), 4)
    return metrics

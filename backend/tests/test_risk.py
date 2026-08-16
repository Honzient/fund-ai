"""风险指标单元测试。"""
import numpy as np
import pandas as pd
import pytest

from app.analytics.risk import (
    beta_alpha,
    compute_risk_metrics,
    cvar_95,
    max_drawdown,
    sharpe_ratio,
    var_95,
)


def test_max_drawdown_known():
    series = pd.Series([100, 120, 90, 110, 80, 100])
    assert max_drawdown(series) == pytest.approx(80 / 120 - 1, rel=1e-6)


def test_sharpe_positive_for_uptrend():
    rets = pd.Series(np.full(252, 0.001) + np.random.default_rng(1).normal(0, 0.0001, 252))
    assert sharpe_ratio(rets) > 1


def test_var_cvar_ordering():
    rng = np.random.default_rng(2)
    rets = pd.Series(rng.normal(0, 0.02, 1000))
    assert var_95(rets) > 0
    assert cvar_95(rets) >= var_95(rets)


def test_beta_alpha_perfect_correlation():
    rng = np.random.default_rng(3)
    bench = pd.Series(rng.normal(0.0005, 0.01, 300))
    fund = 1.5 * bench  # beta = 1.5
    beta, alpha = beta_alpha(fund, bench)
    assert beta == pytest.approx(1.5, rel=0.05)


def test_compute_risk_metrics_keys():
    rng = np.random.default_rng(4)
    nav = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, 400))))
    metrics = compute_risk_metrics(nav)
    for key in ("annual_return", "annual_volatility", "max_drawdown", "sharpe", "sortino",
                "calmar", "var_95", "cvar_95", "best_day", "worst_day"):
        assert key in metrics
    assert metrics["max_drawdown"] <= 0
    assert metrics["annual_volatility"] > 0

"""技术指标单元测试。"""
import numpy as np
import pandas as pd
import pytest

from app.analytics.indicators import bollinger, compute_all, latest_indicators, macd, rsi, sma


@pytest.fixture()
def df():
    dates = pd.bdate_range("2024-01-01", periods=300)
    prices = 100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.0005, 0.01, 300)))
    return pd.DataFrame({"date": dates, "nav": prices})


def test_sma_values(df):
    s = sma(df["nav"], 5)
    assert s.iloc[4] == pytest.approx(df["nav"].iloc[:5].mean(), rel=1e-6)
    assert np.isnan(s.iloc[3])


def test_rsi_bounds_and_uptrend(df):
    up = pd.Series(np.linspace(1, 2, 100))
    r = rsi(up, 14)
    assert r.dropna().iloc[-1] == pytest.approx(100.0, abs=0.01)
    down = pd.Series(np.linspace(2, 1, 100))
    r2 = rsi(down, 14)
    assert r2.dropna().iloc[-1] == pytest.approx(0.0, abs=0.01)


def test_macd_shapes(df):
    dif, dea, hist = macd(df["nav"])
    assert len(dif) == len(df)
    assert np.allclose(hist.iloc[-1], (dif.iloc[-1] - dea.iloc[-1]) * 2, rtol=1e-9)


def test_bollinger_width_positive(df):
    upper, mid, lower = bollinger(df["nav"], 20, 2)
    assert (upper - lower).dropna().min() >= 0


def test_compute_all_columns(df):
    out = compute_all(df)
    for col in ("ma5", "ma20", "ma60", "macd", "rsi14", "bb_upper", "momentum_20d", "vol_20"):
        assert col in out.columns
    latest = latest_indicators(out)
    assert latest["ma20"] is not None
    assert latest["rsi14"] is not None
    # 动量定义: 20日收益
    expected = out["nav"].iloc[-1] / out["nav"].iloc[-21] - 1
    assert latest["momentum_20d"] == pytest.approx(expected, rel=1e-4)

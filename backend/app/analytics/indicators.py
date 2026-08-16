"""技术指标计算（纯函数，pandas/numpy，无未来数据泄露）。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """返回 (DIF, DEA, MACD柱)。"""
    dif = ema(series, fast) - ema(series, slow)
    dea = ema(dif, signal)
    hist = (dif - dea) * 2  # 国内常用 MACD 柱 = 2*(DIF-DEA)
    return dif, dea, hist


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=window, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    # 全部为涨（loss=0）时 RSI=100
    out = out.where(loss != 0, 100.0)
    return out


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std(ddof=0)
    return mid + num_std * std, mid, mid - num_std * std


def atr_proxy(series: pd.Series, window: int = 14) -> pd.Series:
    """净值类资产没有 OHLC，用滚动标准差近似 ATR（文档中明确说明）。"""
    return series.rolling(window=window, min_periods=window).std(ddof=0)


def momentum_return(series: pd.Series, window: int) -> pd.Series:
    """window 日累计收益（小数）。"""
    return series.pct_change(periods=window)


def compute_all(df: pd.DataFrame, price_col: str = "nav") -> pd.DataFrame:
    """为净值 DataFrame 追加全部技术指标列。输入须按日期升序。"""
    out = df.copy()
    price = out[price_col]
    out["ma5"] = sma(price, 5)
    out["ma10"] = sma(price, 10)
    out["ma20"] = sma(price, 20)
    out["ma60"] = sma(price, 60)
    out["ema12"] = ema(price, 12)
    out["ema26"] = ema(price, 26)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(price)
    out["rsi14"] = rsi(price, 14)
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = bollinger(price, 20, 2.0)
    out["atr14"] = atr_proxy(price, 14)
    out["momentum_5d"] = momentum_return(price, 5)
    out["momentum_20d"] = momentum_return(price, 20)
    out["momentum_60d"] = momentum_return(price, 60)
    out["momentum_250d"] = momentum_return(price, 250)
    out["vol_20"] = price.pct_change().rolling(20, min_periods=20).std(ddof=0)
    out["vol_60"] = price.pct_change().rolling(60, min_periods=60).std(ddof=0)
    return out


def latest_indicators(df: pd.DataFrame) -> dict:
    """最新一期的技术指标快照。"""
    computed = compute_all(df) if "ma20" not in df.columns else df
    if computed.empty:
        return {}
    last = computed.iloc[-1]

    def _v(key: str):
        val = last.get(key)
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return None
        if isinstance(val, (np.floating, float)):
            return round(float(val), 6)
        return val

    return {
        "ma5": _v("ma5"), "ma10": _v("ma10"), "ma20": _v("ma20"), "ma60": _v("ma60"),
        "ema12": _v("ema12"), "ema26": _v("ema26"),
        "macd": _v("macd"), "macd_signal": _v("macd_signal"), "macd_hist": _v("macd_hist"),
        "rsi14": _v("rsi14"),
        "bb_upper": _v("bb_upper"), "bb_mid": _v("bb_mid"), "bb_lower": _v("bb_lower"),
        "atr14": _v("atr14"),
        "momentum_5d": _v("momentum_5d"), "momentum_20d": _v("momentum_20d"),
        "momentum_60d": _v("momentum_60d"), "momentum_250d": _v("momentum_250d"),
        "vol_20": _v("vol_20"), "vol_60": _v("vol_60"),
    }


def indicator_series(df: pd.DataFrame, limit: int = 400) -> dict:
    """用于图表的技术指标序列（截取最近 limit 条）。"""
    computed = compute_all(df) if "ma20" not in df.columns else df
    tail = computed.tail(limit)
    out: dict[str, list] = {"date": [d.isoformat() for d in tail["date"]]}
    for col in (
        "ma5", "ma10", "ma20", "ma60", "macd", "macd_signal", "macd_hist",
        "rsi14", "bb_upper", "bb_mid", "bb_lower",
    ):
        series = tail[col]
        out[col] = [None if (v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))))
                    else round(float(v), 6) for v in series]
    return out

"""预测特征工程（严格时间顺序，禁止未来数据泄露）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.indicators import bollinger, macd, rsi, sma

HORIZONS: dict[str, int] = {"short": 5, "medium": 20, "long": 60}
TARGET_THRESHOLDS: dict[str, float] = {"short": 0.005, "medium": 0.02, "long": 0.05}

FEATURE_COLUMNS = [
    "ret_1", "ret_5", "ret_20", "ret_60",
    "rsi14", "macd_hist_norm", "bb_position", "vol_20",
    "dist_ma20", "dist_ma60", "mdd_60",
    "market_ret_5", "market_ret_20",
]


def add_features(df: pd.DataFrame, market_close: pd.Series | None = None) -> pd.DataFrame:
    """为净值序列计算特征。所有特征仅使用当前及历史信息。

    市场特征使用市场收盘价 ffill 对齐（只用已发生的数据）。
    """
    out = df.copy()
    price = out["nav"]
    out["ret_1"] = price.pct_change(1)
    out["ret_5"] = price.pct_change(5)
    out["ret_20"] = price.pct_change(20)
    out["ret_60"] = price.pct_change(60)
    out["rsi14"] = rsi(price, 14)
    _, _, hist = macd(price)
    out["macd_hist_norm"] = hist / price.replace(0, np.nan)
    _, mid, _ = bollinger(price)
    std20 = price.rolling(20, min_periods=20).std(ddof=0)
    out["bb_position"] = (price - mid) / std20.replace(0, np.nan)
    out["vol_20"] = out["ret_1"].rolling(20, min_periods=20).std(ddof=0)
    out["dist_ma20"] = price / sma(price, 20) - 1
    out["dist_ma60"] = price / sma(price, 60) - 1
    out["mdd_60"] = price / price.rolling(60, min_periods=60).max() - 1
    if market_close is not None and not market_close.empty:
        # 用最近已知的市场收盘价（当日或更早），并重置为位置索引以对齐本表
        mkt = market_close.reindex(out["date"]).reset_index(drop=True)
        mkt = mkt.ffill()
        out["market_ret_5"] = mkt.pct_change(5).reset_index(drop=True)
        out["market_ret_20"] = mkt.pct_change(20).reset_index(drop=True)
    else:
        out["market_ret_5"] = np.nan
        out["market_ret_20"] = np.nan
    return out


def make_labels(future_ret: pd.Series, horizon: str) -> pd.Series:
    """方向标签：2=上涨, 1=震荡, 0=下跌。"""
    thr = TARGET_THRESHOLDS[horizon]
    labels = pd.Series(1, index=future_ret.index)
    labels[future_ret > thr] = 2
    labels[future_ret < -thr] = 0
    labels[future_ret.isna()] = np.nan
    return labels


def build_dataset(
    fund_dfs: dict[str, pd.DataFrame],
    market_close: pd.Series | None,
    horizon: str,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame] | None:
    """汇总全市场样本。features 全部来自 t 时刻及以前，labels 来自 t+h（仅用于训练）。"""
    horizon_days = HORIZONS[horizon]
    frames: list[pd.DataFrame] = []
    for fund_code, df in fund_dfs.items():
        if len(df) < 140:
            continue
        feats = add_features(df.sort_values("date"), market_close)
        price = feats["nav"]
        future_ret = price.shift(-horizon_days) / price - 1
        feats["label"] = make_labels(future_ret, horizon)
        feats = feats.dropna(subset=FEATURE_COLUMNS + ["label"])
        feats["fund_code"] = fund_code
        frames.append(feats)
    if not frames:
        return None
    all_df = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    if all_df.empty:
        return None
    X = all_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = all_df["label"].to_numpy(dtype=int)
    return X, y, all_df


def current_features(
    df: pd.DataFrame, market_close: pd.Series | None = None
) -> dict[str, float] | None:
    """最新一期的特征向量（用于预测当前时点）。"""
    if len(df) < 140:
        return None
    feats = add_features(df.sort_values("date"), market_close)
    row = feats.iloc[-1]
    values: dict[str, float] = {}
    for col in FEATURE_COLUMNS:
        v = row.get(col)
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return None
        values[col] = float(v)
    return values

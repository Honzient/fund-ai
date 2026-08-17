"""Baseline 策略：模型必须与朴素方法对比才有意义。

- majority：恒预测训练集众数类别
- random：随机均匀预测（对照下界）
- momentum：20 日动量为正 → up，为负 → down，否则 range
- simple_trend：价格相对 MA20 的偏离方向（t>0 up / t<0 down / 0 range）
- always_up：恒 up（买入持有方向基准）

输入为含特征列的 DataFrame（至少需要 ret_20 / dist_ma20），
输出与模型预测相同的类别编码：0=down, 1=range, 2=up。
"""
from __future__ import annotations

import numpy as np

BASELINE_NAMES = ("majority", "random", "momentum", "simple_trend", "always_up")


def _majority_class(y_train: np.ndarray) -> int:
    counts = np.bincount(np.asarray(y_train, dtype=int), minlength=3)
    return int(np.argmax(counts))


def baselines_for_frame(name: str, frame, y_train: np.ndarray, seed: int = 42) -> np.ndarray:
    """按 DataFrame 列名定位特征列并预测。"""
    n = len(frame)
    if name == "majority":
        return np.full(n, _majority_class(y_train), dtype=int)
    if name == "random":
        return np.random.default_rng(seed).integers(0, 3, size=n).astype(int)
    if name == "always_up":
        return np.full(n, 2, dtype=int)
    if name == "momentum":
        col = "ret_20" if "ret_20" in frame.columns else None
        up_thr, down_thr = 0.005, -0.005
    elif name == "simple_trend":
        col = "dist_ma20" if "dist_ma20" in frame.columns else None
        up_thr, down_thr = 0.0, 0.0
    else:
        raise ValueError(f"未知 baseline: {name}")
    if col is None:
        return np.full(n, _majority_class(y_train), dtype=int)
    vals = frame[col].to_numpy(dtype=float)
    out = np.where(vals > up_thr, 2, np.where(vals < down_thr, 0, 1)).astype(int)
    return np.where(np.isnan(vals), 1, out)

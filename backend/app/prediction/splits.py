"""Purged Walk-Forward 时间序列切分（防未来数据泄露）。

与普通 TimeSeriesSplit 的关键区别：
- 按交易日分组切分（而不是按样本序号）；
- embargo：训练集结束与测试集开始之间强制间隔 horizon 个交易日；
- purge：训练集尾部再剔除 horizon-1 个交易日，保证训练样本的标签窗口
  [t, t+horizon) 与测试期零交集；
- 扩展窗口（walk-forward），fold 越多测试段越细。

用途：交叉验证、概率校准的 OOF 预测、模型对比与回测。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass
class PurgedTimeSeriesSplit:
    dates: np.ndarray  # 与样本对齐的日期数组（须已按时间升序）
    n_splits: int = 5
    horizon: int = 5  # 标签窗口（交易日）
    embargo: int | None = None  # 训练/测试间隔（交易日），默认 = horizon
    purge: int | None = None  # 训练尾部剔除窗口，默认 = horizon - 1
    min_train: int = 60  # 最小训练样本数（不足则跳过该 fold）

    def __post_init__(self) -> None:
        self.dates = np.asarray(self.dates)
        if len(self.dates) == 0:
            raise ValueError("dates 不能为空")
        if not np.all(np.diff(self.dates) >= np.timedelta64(0, "D")):
            raise ValueError("dates 必须按时间升序排列")
        self.embargo = self.horizon if self.embargo is None else self.embargo
        self.purge = max(self.horizon - 1, 0) if self.purge is None else self.purge

    def split(self, X=None, y=None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:  # noqa: ARG002
        unique_dates = np.unique(self.dates)
        n_days = len(unique_dates)
        if n_days < self.n_splits + 1:
            raise ValueError("日期数量不足以进行切分")
        test_size = max(n_days // (self.n_splits + 1), 1)
        for i in range(self.n_splits):
            test_start_pos = n_days - (self.n_splits - i) * test_size
            test_end_pos = min(test_start_pos + test_size, n_days)
            train_end_pos = test_start_pos - self.embargo - self.purge
            if train_end_pos <= 1:
                continue
            test_dates = set(unique_dates[test_start_pos:test_end_pos])
            train_last_date = unique_dates[train_end_pos - 1]
            train_idx = np.where(self.dates <= train_last_date)[0]
            test_idx = np.where(np.isin(self.dates, list(test_dates)))[0]
            if len(train_idx) < self.min_train or len(test_idx) == 0:
                continue
            yield train_idx, test_idx

    def get_n_splits(self, X=None, y=None, groups=None) -> int:  # noqa: ARG002
        return self.n_splits


def assert_no_label_overlap(
    dates: np.ndarray,
    splits: list[tuple[np.ndarray, np.ndarray]],
    horizon: int,
) -> bool:
    """校验：每个 fold 的训练样本标签窗口 [t, t+horizon) 与测试日期零交集。

    dates 为交易日数组；标签窗口按"交易日序"近似（用日期位置索引）。
    返回 True 表示无重叠。
    """
    unique_dates = np.unique(dates)
    pos = {d: i for i, d in enumerate(unique_dates)}
    for train_idx, test_idx in splits:
        train_positions = np.array([pos[d] for d in dates[train_idx]])
        test_positions = np.array([pos[d] for d in dates[test_idx]])
        if len(train_positions) == 0 or len(test_positions) == 0:
            continue
        max_label_end = train_positions.max() + horizon  # 标签窗口覆盖到该位置
        if max_label_end > test_positions.min():
            return False
    return True

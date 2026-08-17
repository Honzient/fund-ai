"""概率校准：把模型输出的分数（raw probability）校准为可信概率。

- 逐类（one-vs-rest）在校准集上拟合 sigmoid（Platt）或 isotonic；
- 校准集来自 Purged 交叉验证的 OOF 预测（避免自拟合）；
- 输出逐类归一化（和为 1）；
- 校准集样本不足时自动降级 `uncalibrated`，并在结果中显式标记。
"""
from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from app.core.logging import get_logger

log = get_logger("app.prediction")

MIN_CALIBRATION_SAMPLES = 300


class ProbabilityCalibrator:
    def __init__(self, method: str = "isotonic"):
        if method not in ("sigmoid", "isotonic", "uncalibrated"):
            raise ValueError(f"未知校准方法: {method}")
        self.method = method
        self.calibrators_: list | None = None
        self.n_classes_ = 3

    # ------------------------------------------------------------ 拟合

    def fit(self, y_true: np.ndarray, y_proba: np.ndarray) -> "ProbabilityCalibrator":
        """在校准集上拟合。样本不足自动降级。"""
        y_true = np.asarray(y_true).astype(int)
        y_proba = np.asarray(y_proba, dtype=float)
        if y_proba.ndim != 2 or y_proba.shape[1] < 2:
            raise ValueError("y_proba 必须为 (n, k) 概率矩阵")
        self.n_classes_ = y_proba.shape[1]
        if len(y_true) < MIN_CALIBRATION_SAMPLES:
            log.warning(
                "校准样本 %d < %d，降级为 uncalibrated",
                len(y_true), MIN_CALIBRATION_SAMPLES,
            )
            self.method = "uncalibrated"
            self.calibrators_ = None
            return self
        calibrators: list = []
        for k in range(self.n_classes_):
            binary = (y_true == k).astype(int)
            p = y_proba[:, k]
            try:
                if self.method == "isotonic":
                    calibrators.append(
                        IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p, binary)
                    )
                else:
                    calibrators.append(
                        LogisticRegression(C=100.0, max_iter=1000).fit(p.reshape(-1, 1), binary)
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("类别 %d 校准失败（%s），该类退化为原值", k, exc)
                calibrators.append(None)
        self.calibrators_ = calibrators
        return self

    # ------------------------------------------------------------ 预测

    def predict(self, y_proba: np.ndarray) -> np.ndarray:
        """对概率矩阵逐类校准后归一化。"""
        y_proba = np.asarray(y_proba, dtype=float)
        if self.method == "uncalibrated" or self.calibrators_ is None:
            return y_proba.copy()
        out = np.zeros_like(y_proba)
        for k, cal in enumerate(self.calibrators_):
            if cal is None:
                out[:, k] = y_proba[:, k]
            elif self.method == "isotonic":
                out[:, k] = cal.transform(y_proba[:, k])
            else:
                out[:, k] = cal.predict_proba(y_proba[:, k].reshape(-1, 1))[:, 1]
        # 归一化（和为 1）
        totals = out.sum(axis=1, keepdims=True)
        totals[totals == 0] = 1.0
        return out / totals

    # ------------------------------------------------------------ 状态

    def info(self) -> dict:
        return {
            "method": self.method,
            "n_classes": self.n_classes_,
            "degraded": self.method == "uncalibrated",
        }

    def save(self, path) -> None:
        import joblib

        joblib.dump({"method": self.method, "calibrators": self.calibrators_, "n_classes": self.n_classes_}, path)

    @classmethod
    def load(cls, path) -> "ProbabilityCalibrator":
        import joblib

        data = joblib.load(path)
        cal = cls(method=data["method"])
        cal.calibrators_ = data["calibrators"]
        cal.n_classes_ = data["n_classes"]
        return cal

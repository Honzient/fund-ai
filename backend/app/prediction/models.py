"""模型层：Logistic Regression / Random Forest（可扩展 XGBoost/LightGBM）。

第一版不追求深度学习：样本量小、可解释性优先。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression


class BaseModel(ABC):
    name: str = "base"

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> None: ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def feature_importances(self) -> np.ndarray: ...


class LogisticModel(BaseModel):
    name = "logistic"

    def __init__(self) -> None:
        # sklearn>=1.9：multinomial 为默认唯一行为，不再传 multi_class 参数
        self._model = LogisticRegression(
            max_iter=3000, class_weight="balanced", C=1.0, solver="lbfgs",
        )

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model.fit(X, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)

    def feature_importances(self) -> np.ndarray:
        coef = np.abs(self._model.coef_).mean(axis=0)
        total = coef.sum()
        return coef / total if total > 0 else coef


class RandomForestModel(BaseModel):
    name = "random_forest"

    def __init__(self) -> None:
        from app.core.config import get_settings

        self._model = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=20,
            class_weight="balanced_subsample", random_state=42,
            n_jobs=get_settings().MODEL_JOBS,
        )

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._model.fit(X, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)

    def feature_importances(self) -> np.ndarray:
        return self._model.feature_importances_


MODEL_CLASSES: dict[str, type[BaseModel]] = {
    "logistic": LogisticModel,
    "random_forest": RandomForestModel,
}


def get_model(name: str) -> BaseModel:
    cls = MODEL_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"未知模型类型: {name}")
    return cls()


def choose_model(n_samples: int) -> str:
    """按样本量选择模型：样本较少用 LR（更稳），充足用 RF。"""
    from app.core.config import get_settings

    if n_samples >= get_settings().RF_MIN_SAMPLES:
        return "random_forest"
    return "logistic"

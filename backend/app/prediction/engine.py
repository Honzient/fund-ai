"""预测引擎：模型训练（时间序列验证）、概率预测、回测、统计基线降级。

核心原则：
- 只输出概率 / 评分 / 置信度，绝不输出确定涨跌；
- 训练与回测使用 TimeSeriesSplit / Walk-Forward，禁止随机切分；
- 特征仅使用 t 时刻及以前数据，标签来自未来仅用于训练评估；
- 数据不足或模型不可用时降级为统计基线（历史条件分布），置信度封顶 low/medium。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import TimeSeriesSplit

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Fund, FundDailyData, MarketIndexData
from app.prediction.features import (
    FEATURE_COLUMNS,
    HORIZONS,
    TARGET_THRESHOLDS,
    build_dataset,
    current_features,
    make_labels,
)
from app.prediction.models import BaseModel, choose_model, get_model
from app.prediction.registry import ModelRegistry
from app.utils.dates import utcnow

log = get_logger("app.prediction")

DISCLAIMER = (
    "历史回测不代表未来表现；本结果仅为基于历史数据的概率估计与情景分析，"
    "不构成投资建议，不承诺任何收益。"
)

_LABEL_TO_CLASS = {2: "up", 1: "range", 0: "down"}
_CLASS_TO_DIRECTION = {"up": "偏多", "range": "中性", "down": "偏空"}


def _load_fund_history(fund_code: str, years: float = 4.0) -> pd.DataFrame | None:
    db = SessionLocal()
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund is None:
            return None
        start = date.today() - timedelta(days=int(years * 365))
        rows = (
            db.query(FundDailyData)
            .filter(FundDailyData.fund_id == fund.id, FundDailyData.date >= start)
            .order_by(FundDailyData.date)
            .all()
        )
        if len(rows) < 120:
            return None
        return pd.DataFrame(
            {
                "date": [r.date for r in rows],
                "nav": [float(r.nav) for r in rows],
            }
        )
    finally:
        db.close()


def _load_market_close() -> pd.Series | None:
    """默认基准：沪深300；无数据时用第一个可用指数。"""
    db = SessionLocal()
    try:
        idx = db.query(MarketIndexData).join(
            MarketIndexData.index
        ).filter_by(index_code="000300").order_by(MarketIndexData.date).all()
        if not idx:
            return None
        return pd.Series(
            [float(r.close) for r in idx],
            index=pd.Index([r.date for r in idx], name="date"),
        )
    finally:
        db.close()


def _load_all_histories(years: float = 4.0) -> tuple[dict[str, pd.DataFrame], pd.Series | None]:
    db = SessionLocal()
    try:
        start = date.today() - timedelta(days=int(years * 365))
        rows = (
            db.query(FundDailyData, Fund.fund_code)
            .join(Fund, FundDailyData.fund_id == Fund.id)
            .filter(FundDailyData.date >= start)
            .order_by(FundDailyData.date)
            .all()
        )
        frames: dict[str, list[tuple[date, float]]] = {}
        for row, code in rows:
            frames.setdefault(code, []).append((row.date, float(row.nav)))
        funds: dict[str, pd.DataFrame] = {}
        for code, items in frames.items():
            if len(items) >= 120:
                funds[code] = pd.DataFrame(items, columns=["date", "nav"])
    finally:
        db.close()
    return funds, _load_market_close()


class PredictionEngine:
    def __init__(self, registry: ModelRegistry | None = None):
        self.registry = registry or ModelRegistry()
        self.settings = get_settings()

    # ------------------------------------------------------------ 训练

    def _training_data(self, horizon: str):
        funds, market = _load_all_histories()
        return build_dataset(funds, market, horizon)

    def _validate(self, model: BaseModel, X: np.ndarray, y: np.ndarray) -> dict:
        """时间序列交叉验证（按时间顺序切分，最后一个 fold 作为验证集报告）。"""
        n = len(X)
        if n < 90:
            return {"accuracy": None, "up_precision": None, "down_precision": None, "samples": n}
        tscv = TimeSeriesSplit(n_splits=min(3, max(2, n // 120)))
        fold_metrics: list[dict] = []
        for train_idx, val_idx in tscv.split(X):
            if len(val_idx) < 10:
                continue
            m = get_model(model.name)
            m.fit(X[train_idx], y[train_idx])
            pred = np.argmax(m.predict_proba(X[val_idx]), axis=1)
            truth = y[val_idx]
            fold_metrics.append(
                {
                    "accuracy": float(accuracy_score(truth, pred)),
                    "up_precision": float(precision_score(truth, pred, labels=[2], average=None, zero_division=0)[0]),
                    "down_precision": float(precision_score(truth, pred, labels=[0], average=None, zero_division=0)[0]),
                }
            )
        if not fold_metrics:
            return {"accuracy": None, "up_precision": None, "down_precision": None, "samples": n}
        return {
            "accuracy": round(float(np.mean([m["accuracy"] for m in fold_metrics])), 4),
            "up_precision": round(float(np.mean([m["up_precision"] for m in fold_metrics])), 4),
            "down_precision": round(float(np.mean([m["down_precision"] for m in fold_metrics])), 4),
            "samples": n,
        }

    def train(self, horizon: str) -> dict | None:
        """训练并保存新版本模型。数据不足返回 None（调用方降级为统计基线）。"""
        data = self._training_data(horizon)
        if data is None:
            log.warning("训练数据不足，跳过 %s 周期模型训练", horizon)
            return None
        X, y, _ = data
        if len(X) < self.settings.MODEL_MIN_SAMPLES:
            log.warning("样本数 %d < %d，跳过 %s 周期模型训练", len(X), self.settings.MODEL_MIN_SAMPLES, horizon)
            return None

        model_name = choose_model(len(X))
        model = get_model(model_name)
        # 用全部数据训练最终模型（验证指标来自时间序列交叉验证）
        model.fit(X, y)
        metrics = self._validate(model, X, y)
        importances = model.feature_importances()
        importance_list = sorted(
            [
                {"feature": col, "importance": round(float(imp), 4)}
                for col, imp in zip(FEATURE_COLUMNS, importances)
            ],
            key=lambda x: -x["importance"],
        )
        version = self.registry.next_version()
        meta = {
            "version": version,
            "horizon": horizon,
            "horizon_days": HORIZONS[horizon],
            "model": model_name,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "samples": len(X),
            "features": FEATURE_COLUMNS,
            "metrics": metrics,
            "feature_importance": importance_list,
            "validation": "TimeSeriesSplit（时间顺序，无随机切分）",
        }
        self.registry.save(model, meta, horizon, version)
        return meta

    def get_or_train(self, horizon: str) -> tuple[BaseModel, dict] | None:
        """优先加载最新模型；过期或缺失时重新训练。"""
        loaded = self.registry.latest(horizon)
        if loaded is not None:
            model, meta = loaded
            try:
                trained_at = datetime.fromisoformat(str(meta.get("trained_at", "")))
            except ValueError:
                trained_at = None
            if trained_at and (utcnow() - trained_at).days < self.settings.MODEL_RETRAIN_DAYS:
                return model, meta
        return self._load_after_train(horizon)

    def _load_after_train(self, horizon: str) -> tuple[BaseModel, dict] | None:
        meta = self.train(horizon)
        if meta is None:
            return None
        loaded = self.registry.load(meta["version"], horizon)
        return loaded

    # ------------------------------------------------------------ 预测

    def _confidence(self, prob_margin: float, val_accuracy: float | None) -> tuple[str, float]:
        if val_accuracy is None:
            val_accuracy = 0.5
        score = 0.3 + max(0.0, val_accuracy - 0.4) * 0.5 + prob_margin * 0.35
        score = float(np.clip(score, 0.1, 0.95))
        label = "high" if score >= 0.62 else ("medium" if score >= 0.45 else "low")
        return label, round(score, 3)

    def predict(self, fund_code: str, horizon: str) -> dict:
        """模型概率预测；模型不可用/数据不足时降级为统计基线。"""
        df = _load_fund_history(fund_code)
        result_base = {
            "fund_code": fund_code,
            "horizon": horizon,
            "horizon_days": HORIZONS[horizon],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_as_of": df["date"].iloc[-1].isoformat() if df is not None and not df.empty else None,
            "model_version": "baseline",
        }
        if df is None:
            return {
                **result_base,
                "probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                "direction": "中性",
                "confidence": "low",
                "confidence_score": 0.2,
                "feature_importance": [],
                "note": "历史数据不足，无法给出有意义的概率估计，请谨慎参考",
                "disclaimer": DISCLAIMER,
            }
        loaded = self.get_or_train(horizon)
        if loaded is None:
            return {**result_base, **self._baseline_predict(df, horizon)}
        model, meta = loaded
        market = _load_market_close()
        feats = current_features(df, market)
        if feats is None:
            return {**result_base, **self._baseline_predict(df, horizon)}
        X = np.array([[feats[c] for c in FEATURE_COLUMNS]])
        proba = model.predict_proba(X)[0]
        classes = list(getattr(model._model, "classes_", [0, 1, 2]))  # noqa: SLF001
        prob_map = {int(cls): float(p) for cls, p in zip(classes, proba)}
        p_up = prob_map.get(2, 0.0)
        p_range = prob_map.get(1, 0.0)
        p_down = prob_map.get(0, 0.0)
        total = p_up + p_range + p_down or 1.0
        p_up, p_range, p_down = p_up / total, p_range / total, p_down / total
        margin = max(p_up, p_range, p_down) - sorted((p_up, p_range, p_down))[1]
        val_acc = (meta.get("metrics") or {}).get("accuracy")
        conf_label, conf_score = self._confidence(margin, val_acc)
        direction = _CLASS_TO_DIRECTION[_LABEL_TO_CLASS[int(np.argmax([p_down, p_range, p_up]))]]
        return {
            **result_base,
            "model_version": meta["version"],
            "probabilities": {
                "up": round(p_up * 100, 1),
                "range": round(p_range * 100, 1),
                "down": round(p_down * 100, 1),
            },
            "direction": direction,
            "confidence": conf_label,
            "confidence_score": conf_score,
            "feature_importance": meta.get("feature_importance", [])[:8],
            "model": meta.get("model"),
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------------ 统计基线

    def _baseline_predict(self, df: pd.DataFrame, horizon: str) -> dict:
        """统计基线：基于该基金自身历史的条件分布，明确标注低置信度。"""
        thr = TARGET_THRESHOLDS[horizon]
        h = HORIZONS[horizon]
        price = df["nav"]
        ret = price.pct_change()
        mom20 = price.pct_change(20)
        fwd = price.shift(-h) / price - 1
        table = pd.DataFrame({"mom20": mom20, "fwd": fwd}).dropna()
        if len(table) < 60:
            table = pd.DataFrame({"fwd": fwd}).dropna()
            cond = table["fwd"]
        else:
            cond = table.loc[table["mom20"] > 0, "fwd"]
            if len(cond) < 40:
                cond = table["fwd"]
        if len(cond) < 20:
            return {
                "probabilities": {"up": 33.3, "range": 33.4, "down": 33.3},
                "direction": "中性",
                "confidence": "low",
                "confidence_score": 0.2,
                "note": "样本过少，仅按均匀分布估计",
                "disclaimer": DISCLAIMER,
            }
        p_up = float((cond > thr).mean())
        p_down = float((cond < -thr).mean())
        p_range = float(1 - p_up - p_down)
        margin = max(p_up, p_range, p_down) - sorted((p_up, p_range, p_down))[1]
        conf_label, conf_score = self._confidence(min(margin, 0.15), 0.48)
        if conf_label == "high":
            conf_label = "medium"  # 基线置信度封顶 medium
        direction = _CLASS_TO_DIRECTION[
            _LABEL_TO_CLASS[int(np.argmax([p_down, p_range, p_up]))]
        ]
        return {
            "model_version": "baseline",
            "probabilities": {
                "up": round(p_up * 100, 1),
                "range": round(p_range * 100, 1),
                "down": round(p_down * 100, 1),
            },
            "direction": direction,
            "confidence": conf_label,
            "confidence_score": conf_score,
            "note": "统计基线估计（模型训练数据不足），基于该基金自身历史条件分布，置信度较低",
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------------ 回测

    def backtest(self, horizon: str, version: str | None = None) -> dict | None:
        """Walk-Forward 回测：滚动重训练 + 前向预测（禁止使用未来数据）。"""
        data = self._training_data(horizon)
        if data is None:
            return None
        X, y, frame = data
        horizon_days = HORIZONS[horizon]
        thr = TARGET_THRESHOLDS[horizon]
        min_train = max(120, self.settings.MODEL_MIN_SAMPLES)
        if len(X) <= min_train + 30:
            return {
                "version": version or "n/a",
                "available": False,
                "reason": "样本不足，无法进行回测",
                "disclaimer": DISCLAIMER,
            }
        model_name = choose_model(len(X))
        train_end = min_train
        step = max(30, min(90, (len(X) - min_train) // 6))
        preds: list[int] = []
        truths: list[int] = []
        fwd_rets: list[float] = []
        while train_end + step <= len(X):
            model = get_model(model_name)
            model.fit(X[:train_end], y[:train_end])
            batch = X[train_end : train_end + step]
            batch_y = y[train_end : train_end + step]
            proba = model.predict_proba(batch)
            preds.extend(np.argmax(proba, axis=1).tolist())
            truths.extend(batch_y.tolist())
            # 对应期间的前向收益（frame 已含全部特征，需重建 fwd）
            train_end += step
        if len(preds) < 20:
            return {"version": version or "n/a", "available": False, "reason": "回测样本不足", "disclaimer": DISCLAIMER}
        preds_arr = np.array(preds)
        truths_arr = np.array(truths)
        accuracy = float(accuracy_score(truths_arr, preds_arr))
        up_recall = float(recall_score(truths_arr, preds_arr, labels=[2], average=None, zero_division=0)[0])
        down_recall = float(recall_score(truths_arr, preds_arr, labels=[0], average=None, zero_division=0)[0])
        # 按预测方向统计：预测"上涨"期间的样本前向收益（用 frame 的 label 列近似方向收益）
        up_mask = preds_arr == 2
        up_period_ret = None
        if up_mask.sum() >= 3:
            # frame 行序与 X 对齐（最后一段），用 label 还原方向占比，此处用"预测上涨的胜率"
            up_period_ret = float((truths_arr[up_mask] == 2).mean())
        return {
            "version": version or "latest",
            "available": True,
            "horizon": horizon,
            "horizon_days": horizon_days,
            "period_start": None,
            "samples": len(preds),
            "metrics": {
                "direction_accuracy": round(accuracy * 100, 2),
                "up_recall": round(up_recall * 100, 2),
                "down_recall": round(down_recall * 100, 2),
                "up_hit_rate": round((up_period_ret or 0) * 100, 2),
            },
            "note": "Walk-Forward 滚动回测（按时间顺序训练与预测）",
            "disclaimer": DISCLAIMER,
        }

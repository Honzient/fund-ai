"""预测引擎 v0.2。

流水线：
Raw Data → FeatureStore → Purged Walk-Forward CV（embargo+purge，无标签重叠）
→ 候选模型与 Baseline 评测（完整指标 + ModelScore）
→ Champion 选择 → OOF 概率校准（isotonic/sigmoid，样本不足自动 uncalibrated）
→ 模型注册表（语义版本、数据集/特征/校准版本、状态、champion）
→ 预测（**绝不内联训练**：模型未就绪 → 统计基线 + 明确标注）
→ Prediction Ledger 持久化 → 未来数据回填评价。

原则：宁愿模型表现一般，也不产生虚假的高准确率。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prediction.baselines import BASELINE_NAMES, baselines_for_frame, _majority_class
from app.prediction.calibration import ProbabilityCalibrator
from app.prediction.feature_store import DATASET_VERSION, FEATURE_VERSION, FeatureStore
from app.prediction.features import HORIZONS, TARGET_THRESHOLDS
from app.prediction.metrics import calibration_metrics, evaluate_model
from app.prediction.models import BaseModel, get_model
from app.prediction.registry import ModelRegistry
from app.prediction.splits import PurgedTimeSeriesSplit

log = get_logger("app.prediction")

DISCLAIMER = (
    "历史回测不代表未来表现；本结果仅为基于历史数据的概率估计与情景分析，"
    "不构成投资建议，不承诺任何收益。"
)

_LABEL_TO_CLASS = {2: "up", 1: "range", 0: "down"}
_CLASS_TO_DIRECTION = {"up": "偏多", "range": "中性", "down": "偏空"}

MODEL_CANDIDATES = ("logistic", "random_forest")


class PredictionEngine:
    def __init__(self, registry: ModelRegistry | None = None, store: FeatureStore | None = None):
        self.registry = registry or ModelRegistry()
        self.store = store or FeatureStore()
        self.settings = get_settings()
        self._train_lock = threading.Lock()

    # ------------------------------------------------------------ 数据集

    def _dataset(self, horizon: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame] | None:
        data = self.store.build_dataset(horizon, years=self.settings.DATASET_YEARS)
        if data is None:
            return None
        frame, y, dates = data
        if len(frame) < self.settings.MODEL_MIN_SAMPLES:
            log.warning("样本数 %d < %d，无法训练", len(frame), self.settings.MODEL_MIN_SAMPLES)
            return None
        X = frame[self.store.feature_columns].to_numpy(dtype=float)
        return X, y, dates, frame

    # ------------------------------------------------------------ 候选评测

    def _fold_pipeline(self, X_train: np.ndarray, X_test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """fold 内：中位数填充 + 标准化，统计量只来自训练集（防预处理泄露）。"""
        medians = np.nanmedian(X_train, axis=0)
        medians = np.where(np.isnan(medians), 0.0, medians)
        X_train_f = np.where(np.isnan(X_train), medians, X_train)
        X_test_f = np.where(np.isnan(X_test), medians, X_test)
        scaler = StandardScaler().fit(X_train_f)
        return scaler.transform(X_train_f), scaler.transform(X_test_f)

    def evaluate_candidates(self, horizon: str) -> dict | None:
        """Purged CV 评测所有模型候选与 Baseline，选出 Champion。"""
        data = self._dataset(horizon)
        if data is None:
            return None
        X, y, dates, frame = data
        h = HORIZONS[horizon]
        splitter = PurgedTimeSeriesSplit(dates, n_splits=self.settings.CV_N_SPLITS, horizon=h)
        collected: dict[str, dict] = {
            name: {"y_true": [], "y_pred": [], "y_proba": [], "fwd": []}
            for name in MODEL_CANDIDATES + BASELINE_NAMES
        }
        folds = 0
        for train_idx, test_idx in splitter.split(X, y):
            if len(train_idx) < max(60, self.settings.MODEL_MIN_SAMPLES // 2):
                continue
            X_train_f, X_test_f = self._fold_pipeline(X[train_idx], X[test_idx])
            y_train = y[train_idx]
            test_frame = frame.iloc[test_idx]
            test_fwd = frame["fwd_ret"].to_numpy()[test_idx]
            for name in MODEL_CANDIDATES:
                model = get_model(name)
                model.fit(X_train_f, y_train)
                proba = model.predict_proba(X_test_f)
                pred = np.argmax(proba, axis=1)
                c = collected[name]
                c["y_true"].append(y[test_idx])
                c["y_pred"].append(pred)
                c["y_proba"].append(proba)
                c["fwd"].append(test_fwd)
            for base in BASELINE_NAMES:
                pred = baselines_for_frame(base, test_frame, y_train)
                c = collected[base]
                c["y_true"].append(y[test_idx])
                c["y_pred"].append(pred)
                c["fwd"].append(test_fwd)
            folds += 1
        if folds == 0:
            return None

        results: dict[str, dict] = {}
        oof: dict[str, Any] = {}
        for name, c in collected.items():
            y_true = np.concatenate(c["y_true"])
            y_pred = np.concatenate(c["y_pred"])
            fwd = np.concatenate(c["fwd"])
            proba = np.vstack(c["y_proba"]) if c["y_proba"] else None
            results[name] = {"metrics": evaluate_model(y_true, y_pred, proba, fwd), "samples": len(y_true)}
            if name in MODEL_CANDIDATES and proba is not None:
                oof[name] = (y_true, proba)
        model_names = [n for n in MODEL_CANDIDATES if n in results]
        if not model_names:
            return None
        champion = max(model_names, key=lambda n: results[n]["metrics"].get("model_score", 0))
        return {
            "horizon": horizon,
            "folds": folds,
            "candidates": results,
            "champion": champion,
            "oof": oof.get(champion),
            "training_end": str(np.max(dates)),
            "n_samples": int(len(X)),
        }

    # ------------------------------------------------------------ 训练

    def train(self, horizon: str) -> dict | None:
        """训练 Champion 模型 + 校准 + 注册（后台线程调用；禁止在请求线程内调用）。"""
        with self._train_lock:
            eval_result = self.evaluate_candidates(horizon)
            if eval_result is None:
                log.warning("训练数据不足，跳过 %s 周期训练", horizon)
                return None
            champion_name = eval_result["champion"]
            data = self._dataset(horizon)
            if data is None:
                return None
            X, y, _dates, _frame = data
            medians = np.nanmedian(X, axis=0)
            medians = np.where(np.isnan(medians), 0.0, medians)
            X_f = np.where(np.isnan(X), medians, X)
            scaler = StandardScaler().fit(X_f)
            X_scaled = scaler.transform(X_f)
            model: BaseModel = get_model(champion_name)
            model.fit(X_scaled, y)

            calibrator = ProbabilityCalibrator(method=self.settings.CALIBRATION_METHOD)
            cal_metrics = eval_result["candidates"][champion_name]["metrics"]
            calibration_info: dict = {}
            if eval_result["oof"] is not None:
                oof_y, oof_proba = eval_result["oof"]
                calibrator.fit(oof_y, oof_proba)
                if calibrator.method != "uncalibrated":
                    cal_proba = calibrator.predict(oof_proba)
                    cal_metrics = evaluate_model(oof_y, np.argmax(cal_proba, axis=1), cal_proba, None)
                    calibration_info = calibration_metrics(oof_y, cal_proba)

            version = self.registry.next_version(horizon)
            columns = self.store.feature_columns
            importances = model.feature_importances()
            importance_list = sorted(
                [
                    {"feature": col, "importance": round(float(imp), 4)}
                    for col, imp in zip(columns, importances)
                ],
                key=lambda x: -x["importance"],
            )
            meta = {
                "version": version,
                "horizon": horizon,
                "horizon_days": HORIZONS[horizon],
                "model_name": champion_name,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_end": eval_result["training_end"],
                "samples": int(len(X)),
                "folds": eval_result["folds"],
                "features": columns,
                "feature_version": FEATURE_VERSION,
                "dataset_version": DATASET_VERSION,
                "calibration_method": calibrator.method,
                "calibrated": calibrator.method != "uncalibrated",
                "validation": (
                    f"PurgedTimeSeriesSplit(embargo={HORIZONS[horizon]}, "
                    f"purge={HORIZONS[horizon] - 1}, folds={eval_result['folds']})"
                ),
                "metrics": eval_result["candidates"][champion_name]["metrics"],
                "calibrated_metrics": cal_metrics,
                "calibration": calibration_info,
                "baseline_comparison": {
                    name: res["metrics"] for name, res in eval_result["candidates"].items()
                },
                "feature_importance": importance_list,
                "feature_medians": {c: float(v) for c, v in zip(columns, medians)},
                "feature_mean": {c: float(v) for c, v in zip(columns, scaler.mean_)},
                "feature_scale": {c: float(v) for c, v in zip(columns, scaler.scale_)},
                "status": "active",
                "champion": False,
            }
            self.registry.save(model, meta, horizon, version)
            self.registry.save_calibrator(calibrator, horizon, version)
            self.registry.set_champion(horizon, version)
            log.info(
                "训练完成 %s/%s: %s, ModelScore=%s, Brier=%s, 校准=%s",
                horizon, version, champion_name,
                meta["metrics"].get("model_score"),
                meta["metrics"].get("brier_score"),
                calibrator.method,
            )
            return meta

    # ------------------------------------------------------------ 加载

    def get_champion(self, horizon: str) -> tuple[Any, Any, dict] | None:
        meta = self.registry.get_champion(horizon)
        if meta is None:
            return None
        loaded = self.registry.load(meta["version"], horizon)
        if loaded is None:
            return None
        model, _ = loaded
        calibrator = self.registry.load_calibrator(meta["version"], horizon)
        if calibrator is None:
            calibrator = ProbabilityCalibrator(method="uncalibrated")
        return model, calibrator, meta

    # ------------------------------------------------------------ 预测

    def predict(self, fund_code: str, horizon: str) -> dict:
        """生成预测。模型未就绪/数据不足 → 统计基线并明确标注，绝不阻塞、绝不留空。"""
        base = {
            "fund_code": fund_code,
            "horizon": horizon,
            "horizon_days": HORIZONS[horizon],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_name": None,
            "model_version": "baseline",
            "champion": False,
            "calibration_method": "uncalibrated",
            "calibrated": False,
            "data_as_of": None,
            "feature_snapshot": None,
            "market_snapshot": None,
            "disclaimer": DISCLAIMER,
        }
        row, snapshot = self.store.current_feature_row(fund_code)
        market_snapshot = self.store.market_snapshot()
        if snapshot is not None:
            base["data_as_of"] = snapshot.get("as_of")
        if row is None:
            return {
                **base,
                "raw_probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                "calibrated_probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                "probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                "predicted_class": "range",
                "direction": "中性",
                "confidence": "low",
                "confidence_score": 0.2,
                "feature_importance": [],
                "market_snapshot": market_snapshot,
                "note": "历史数据不足，无法给出有意义的概率估计，请谨慎参考",
            }
        champion = self.get_champion(horizon)
        if champion is None:
            history = self.store._load_fund_histories(4.0).get(fund_code)  # noqa: SLF001
            fallback = (
                self._baseline_predict(history, horizon)
                if history is not None and len(history) >= 60
                else {
                    "raw_probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                    "calibrated_probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                    "probabilities": {"up": 33.3, "range": 33.3, "down": 33.4},
                    "predicted_class": "range",
                    "direction": "中性",
                    "confidence": "low",
                    "confidence_score": 0.2,
                    "calibration_method": "uncalibrated",
                    "calibrated": False,
                    "feature_importance": [],
                    "disclaimer": DISCLAIMER,
                }
            )
            fallback.update(
                {
                    "market_snapshot": market_snapshot,
                    "feature_snapshot": self._compact_snapshot(snapshot),
                    "note": "模型未就绪或训练中，暂用统计基线估计（置信度封顶 medium）",
                }
            )
            return {**base, **fallback}

        model, calibrator, meta = champion
        columns = self.store.feature_columns
        X = np.array([[row.get(c) if row.get(c) is not None else np.nan for c in columns]], dtype=float)
        medians = meta.get("feature_medians", {})
        mean = meta.get("feature_mean", {})
        scale = meta.get("feature_scale", {})
        for i, col in enumerate(columns):
            if np.isnan(X[0, i]):
                X[0, i] = medians.get(col, 0.0)
        for i, col in enumerate(columns):
            m = mean.get(col)
            s = scale.get(col)
            if m is not None and s not in (None, 0.0):
                X[0, i] = (X[0, i] - m) / s
        raw = model.predict_proba(X)[0]
        classes = [int(c) for c in getattr(model._model, "classes_", [0, 1, 2])]  # noqa: SLF001
        prob_map = {cls: float(p) for cls, p in zip(classes, raw)}
        p_down_raw, p_range_raw, p_up_raw = self._normalize(
            (prob_map.get(0, 0.0), prob_map.get(1, 0.0), prob_map.get(2, 0.0))
        )
        calibrated = calibrator.predict(np.array([[p_down_raw, p_range_raw, p_up_raw]]))[0]
        p_down, p_range, p_up = self._normalize(tuple(float(v) for v in calibrated))
        probs = {"up": round(p_up * 100, 1), "range": round(p_range * 100, 1), "down": round(p_down * 100, 1)}
        margin = max(p_up, p_range, p_down) - sorted((p_up, p_range, p_down))[1]
        ece = (meta.get("calibrated_metrics") or {}).get("ece")
        conf_label, conf_score = self._confidence(margin, ece)
        direction = _CLASS_TO_DIRECTION[_LABEL_TO_CLASS[int(np.argmax([p_down, p_range, p_up]))]]
        return {
            **base,
            "model_name": meta.get("model_name"),
            "model_version": meta.get("version"),
            "champion": True,
            "calibration_method": calibrator.method,
            "calibrated": calibrator.method != "uncalibrated",
            "raw_probabilities": {
                "up": round(p_up_raw * 100, 1),
                "range": round(p_range_raw * 100, 1),
                "down": round(p_down_raw * 100, 1),
            },
            "calibrated_probabilities": probs,
            "probabilities": probs,
            "predicted_class": _LABEL_TO_CLASS[int(np.argmax([p_down, p_range, p_up]))],
            "direction": direction,
            "confidence": conf_label,
            "confidence_score": conf_score,
            "feature_importance": meta.get("feature_importance", [])[:10],
            "feature_snapshot": self._compact_snapshot(snapshot),
            "market_snapshot": market_snapshot,
            "note": None,
        }

    @staticmethod
    def _normalize(probs: tuple[float, float, float]) -> tuple[float, float, float]:
        total = sum(probs) or 1.0
        return tuple(p / total for p in probs)

    def _confidence(self, margin: float, ece: float | None) -> tuple[str, float]:
        if ece is None:
            ece = 0.25
        score = 0.35 + margin * 0.4 + (0.25 - min(ece, 0.25)) * 0.8
        score = float(np.clip(score, 0.1, 0.9))
        label = "high" if score >= 0.62 else ("medium" if score >= 0.45 else "low")
        return label, round(score, 3)

    @staticmethod
    def _compact_snapshot(snapshot: dict) -> dict:
        """台账/上下文用的压缩特征快照（值 + 质量）。"""
        compact: dict[str, Any] = {"fund_code": snapshot.get("fund_code"), "as_of": snapshot.get("as_of")}
        for layer, features in (snapshot.get("layers") or {}).items():
            compact[layer] = {
                col: {"value": info.get("value"), "quality": info.get("quality")}
                for col, info in features.items()
                if info.get("quality") != "missing"
            }
        return compact

    # ------------------------------------------------------------ 统计基线

    def _baseline_predict(self, df: pd.DataFrame, horizon: str) -> dict:
        """统计基线：基于该基金自身历史的条件分布，明确标注低置信度。"""
        thr = TARGET_THRESHOLDS[horizon]
        h = HORIZONS[horizon]
        price = df["nav"]
        mom20 = price.pct_change(20)
        fwd = price.shift(-h) / price - 1
        table = pd.DataFrame({"mom20": mom20, "fwd": fwd}).dropna()
        if len(table) < 60:
            cond = pd.DataFrame({"fwd": fwd}).dropna()["fwd"]
        else:
            cond = table.loc[table["mom20"] > 0, "fwd"]
            if len(cond) < 40:
                cond = table["fwd"]
        if len(cond) < 20:
            probs = {"up": 33.3, "range": 33.4, "down": 33.3}
        else:
            p_up = float((cond > thr).mean())
            p_down = float((cond < -thr).mean())
            p_range = float(1 - p_up - p_down)
            probs = {
                "up": round(p_up * 100, 1),
                "range": round(p_range * 100, 1),
                "down": round(p_down * 100, 1),
            }
        direction = _CLASS_TO_DIRECTION[
            _LABEL_TO_CLASS[int(np.argmax([probs["down"], probs["range"], probs["up"]]))]
        ]
        return {
            "model_version": "baseline",
            "raw_probabilities": probs,
            "calibrated_probabilities": probs,
            "probabilities": probs,
            "predicted_class": _LABEL_TO_CLASS[int(np.argmax([probs["down"], probs["range"], probs["up"]]))],
            "direction": direction,
            "confidence": "low",
            "confidence_score": 0.35,
            "calibration_method": "uncalibrated",
            "calibrated": False,
            "feature_importance": [],
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------------ 回测

    def backtest(self, horizon: str, version: str | None = None, model_name: str | None = None) -> dict:
        """Walk-Forward 回测（Purged 窗口）+ 同窗口 Baseline 对比。"""
        data = self._dataset(horizon)
        if data is None:
            return {
                "version": version or "n/a",
                "available": False,
                "reason": "训练样本不足，无法回测",
                "disclaimer": DISCLAIMER,
            }
        X, y, _dates, frame = data
        h = HORIZONS[horizon]
        min_train = max(120, self.settings.MODEL_MIN_SAMPLES)
        step = max(30, min(90, (len(X) - min_train) // 6))
        name = model_name or self.settings.BACKTEST_MODEL
        all_preds: list[int] = []
        all_truth: list[int] = []
        all_fwd: list[float] = []
        n_retrains = 0
        split_pos = min_train
        while split_pos + step <= len(X):
            X_train_f, X_test_f = self._fold_pipeline(X[:split_pos], X[split_pos : split_pos + step])
            model = get_model(name)
            model.fit(X_train_f, y[:split_pos])
            proba = model.predict_proba(X_test_f)
            all_preds.extend(np.argmax(proba, axis=1).tolist())
            all_truth.extend(y[split_pos : split_pos + step].tolist())
            all_fwd.extend(frame["fwd_ret"].to_numpy()[split_pos : split_pos + step].tolist())
            split_pos += step
            n_retrains += 1
        if len(all_preds) < 20:
            return {"version": version or "n/a", "available": False, "reason": "回测样本不足", "disclaimer": DISCLAIMER}
        y_pred = np.array(all_preds)
        y_true = np.array(all_truth)
        fwd = np.array(all_fwd)
        backtest_frame = frame.iloc[min_train : min_train + len(all_preds)]
        baseline_results: dict[str, dict] = {}
        for base in BASELINE_NAMES:
            if base == "majority":
                b_pred = np.full(len(all_preds), _majority_class(y[:min_train]), dtype=int)
            else:
                b_pred = baselines_for_frame(base, backtest_frame, y[:min_train])
            baseline_results[base] = evaluate_model(y_true, b_pred, None, fwd)
        model_metrics = evaluate_model(y_true, y_pred, None, fwd)
        return {
            "version": version or "latest",
            "available": True,
            "horizon": horizon,
            "horizon_days": h,
            "samples": len(all_preds),
            "retrains": n_retrains,
            "metrics": model_metrics,
            "baselines": baseline_results,
            "note": "Walk-Forward 滚动回测（Purged 窗口，按时间顺序训练与预测）",
            "disclaimer": DISCLAIMER,
        }

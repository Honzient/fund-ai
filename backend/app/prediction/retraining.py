"""RetrainingManager：重训入口（手动/定时/表现触发）与模型健康度评估。

- 默认不自动频繁重训；重训保留 dataset/feature/model 版本快照（可重现）；
- 健康度：Champion 元数据 + 台账近 30/100 次真实命中率 vs 验证期表现
  → healthy / warning / degraded；
- 漂移监测（drift）：Performance / Calibration / Feature 三通道，只检测不自动重训；
- 表现显著退化时给出重训建议（是否自动重训由配置决定）。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.prediction.ledger import ledger_stats
from app.prediction.metrics import calibration_metrics, classification_metrics
from app.prediction.registry import ModelRegistry

log = get_logger("app.prediction")

# ------------------------------------------------------------ 漂移阈值（简单稳定统计）

DRIFT_PERF_GAP_DEGRADED = 15.0  # 近30次命中率 vs 验证期：差 ≥15pp → degraded
DRIFT_PERF_GAP_WARNING = 8.0  # ≥8pp → warning
DRIFT_CAL_REL_WARNING = 0.25  # log_loss/brier 相对恶化 ≥25% → warning
DRIFT_CAL_REL_DEGRADED = 0.50  # ≥50% → degraded
DRIFT_CAL_ECE_WARNING = 0.05  # ECE 绝对增加 ≥0.05 → warning
DRIFT_CAL_ECE_DEGRADED = 0.10  # ≥0.10 → degraded
DRIFT_FEATURE_SHIFT = 0.5  # 特征均值偏移 ≥0.5 个训练标准差 → 该特征漂移
DRIFT_FEATURE_WARNING_RATIO = 0.30  # 漂移特征占比 ≥30% → warning
DRIFT_FEATURE_DEGRADED_RATIO = 0.50  # ≥50% → degraded
DRIFT_MIN_CAL_RECORDS = 20  # 校准漂移最少样本
DRIFT_MIN_FEATURE_RECORDS = 10  # 特征漂移最少样本
DRIFT_TOP_FEATURES = 10  # 检查的主要特征数

_STATUS_ORDER = {"degraded": 3, "warning": 2, "healthy": 1}


class RetrainingManager:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.settings = get_settings()
        self._warmup_started = False

    # ------------------------------------------------------------ 重训

    def retrain(self, horizons: list[str] | None = None) -> dict:
        horizons = horizons or ["short", "medium", "long"]
        results: dict[str, dict] = {}
        for h in horizons:
            try:
                meta = self.engine.train(h)
                results[h] = {
                    "trained": meta is not None,
                    "version": meta["version"] if meta else None,
                    "model_name": meta.get("model_name") if meta else None,
                    "samples": (meta or {}).get("samples"),
                    "metrics": (meta or {}).get("metrics"),
                    "calibration_method": (meta or {}).get("calibration_method"),
                }
            except Exception as exc:  # noqa: BLE001
                log.exception("重训失败 %s: %s", h, exc)
                results[h] = {"trained": False, "error": str(exc)[:300]}
        return results

    def warmup(self) -> None:
        """启动预热：后台线程训练缺失的 Champion（不阻塞启动）。"""
        if self._warmup_started or not self.settings.AUTO_WARMUP_TRAIN:
            return
        self._warmup_started = True
        missing = [h for h in ("short", "medium", "long") if self.engine.registry.get_champion(h) is None]
        if not missing:
            return

        def _run():
            log.info("预热训练开始: %s", missing)
            try:
                self.retrain(missing)
            except Exception as exc:  # noqa: BLE001
                log.exception("预热训练异常: %s", exc)

        threading.Thread(target=_run, daemon=True, name="model-warmup").start()

    # ------------------------------------------------------------ 健康度

    def health(self, horizon: str | None = None) -> dict:
        horizons = [horizon] if horizon else ["short", "medium", "long"]
        out: dict = {}
        db = SessionLocal()
        try:
            for h in horizons:
                out[h] = self._health_for(db, h)
        finally:
            db.close()
        return out

    def _health_for(self, db, horizon: str) -> dict:
        registry = ModelRegistry()
        meta = registry.get_champion(horizon) or (
            registry.list_models(horizon)[0] if registry.list_models(horizon) else None
        )
        if meta is None:
            return {"champion": None, "status": "no_model", "note": "尚无可用模型（数据不足或未训练）"}
        metrics = meta.get("calibrated_metrics") or meta.get("metrics") or {}
        historical_hit = metrics.get("hit_rate")
        stats = ledger_stats(db)
        overall = stats.get("overall") or {}
        recent = (overall.get("last_30") or {}).get("hit_rate")
        mid = (overall.get("last_100") or {}).get("hit_rate")
        status = "healthy"
        note = "近30次预测表现与验证期一致"
        if recent is not None and historical_hit is not None:
            gap = historical_hit * 100 - recent
            if gap >= 15:
                status = "degraded"
                note = f"近30次命中率 {recent}% 显著低于验证期 {historical_hit * 100:.0f}%（差 {gap:.0f}pp），建议重训"
            elif gap >= 8:
                status = "warning"
                note = f"近30次命中率 {recent}% 低于验证期 {historical_hit * 100:.0f}%（差 {gap:.0f}pp）"
        elif recent is None:
            status = "insufficient_data"
            note = "台账数据不足，暂无法评估模型真实表现"
        return {
            "horizon": horizon,
            "champion": {
                "model_name": meta.get("model_name"),
                "version": meta.get("version"),
                "trained_at": meta.get("trained_at"),
                "training_end": meta.get("training_end"),
                "calibration_method": meta.get("calibration_method"),
                "model_score": metrics.get("model_score"),
                "metrics": {
                    "brier_score": metrics.get("brier_score"),
                    "log_loss": metrics.get("log_loss"),
                    "balanced_accuracy": metrics.get("balanced_accuracy"),
                    "ece": metrics.get("ece"),
                    "hit_rate": metrics.get("hit_rate"),
                },
                "validation": meta.get("validation"),
                "baseline_comparison": {
                    k: {"model_score": v.get("model_score"), "balanced_accuracy": v.get("balanced_accuracy")}
                    for k, v in (meta.get("baseline_comparison") or {}).items()
                },
            },
            "ledger": {
                "last_30": overall.get("last_30"),
                "last_100": overall.get("last_100"),
                "all": overall.get("all"),
            },
            "status": status,
            "note": note,
            "retrain_recommended": status == "degraded",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------ 漂移监测（v0.3）

    def drift(self, horizon: str | None = None) -> dict:
        """模型漂移监测：Performance / Calibration / Feature 三通道。只检测，不自动重训。"""
        horizons = [horizon] if horizon else ["short", "medium", "long"]
        out: dict = {}
        db = SessionLocal()
        try:
            for h in horizons:
                registry = ModelRegistry()
                meta = registry.get_champion(h) or (
                    registry.list_models(h)[0] if registry.list_models(h) else None
                )
                out[h] = self._drift_for(db, h, meta)
        finally:
            db.close()
        return out

    def _drift_for(self, db, horizon: str, meta: dict | None, fund_id: int | None = None) -> dict:
        if meta is None:
            return {
                "horizon": horizon,
                "champion": None,
                "overall": "no_model",
                "note": "尚无可用模型（数据不足或未训练）",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        validation = meta.get("calibrated_metrics") or meta.get("metrics") or {}
        performance = self._performance_drift(db, horizon, validation, fund_id)
        calibration = self._calibration_drift(db, horizon, validation, fund_id)
        feature = self._feature_drift(db, horizon, meta, fund_id)
        overall = self._overall_status([performance, calibration, feature])
        return {
            "horizon": horizon,
            "champion": {"model_name": meta.get("model_name"), "version": meta.get("version")},
            "performance": performance,
            "calibration": calibration,
            "feature_drift": feature,
            "overall": overall,
            "note": "漂移监测仅做检测，不会自动重训",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _hit_rate(subset) -> float | None:
        if not subset:
            return None
        hits = sum(1 for r in subset if r.predicted_class == r.actual_class)
        return round(hits / len(subset) * 100, 2)

    @staticmethod
    def _recent_records(db, horizon: str, limit: int = 100, fund_id: int | None = None):
        from app.prediction.ledger import PredictionRecord

        q = db.query(PredictionRecord).filter(
            PredictionRecord.horizon == horizon,
            PredictionRecord.actual_class.isnot(None),
        )
        if fund_id is not None:
            q = q.filter(PredictionRecord.fund_id == fund_id)
        return q.order_by(PredictionRecord.prediction_date.desc()).limit(limit).all()

    def _performance_drift(self, db, horizon: str, validation: dict, fund_id: int | None = None) -> dict:
        """Performance Drift：近 30/100 次真实命中率 vs 验证期。"""
        val_hit = validation.get("hit_rate")
        rows = self._recent_records(db, horizon, limit=100, fund_id=fund_id)
        recent_30 = self._hit_rate(rows[:30])
        recent_100 = self._hit_rate(rows[:100])
        if recent_30 is None or val_hit is None:
            return {
                "status": "insufficient_data",
                "validation_hit_rate": val_hit,
                "recent_30_hit_rate": recent_30,
                "recent_100_hit_rate": recent_100,
                "note": "台账或验证期数据不足，无法评估表现漂移",
            }
        gap = val_hit * 100 - recent_30
        if gap >= DRIFT_PERF_GAP_DEGRADED:
            status, note = "degraded", f"近30次命中率 {recent_30}% 显著低于验证期 {val_hit * 100:.0f}%（差 {gap:.0f}pp）"
        elif gap >= DRIFT_PERF_GAP_WARNING:
            status, note = "warning", f"近30次命中率 {recent_30}% 低于验证期 {val_hit * 100:.0f}%（差 {gap:.0f}pp）"
        else:
            status, note = "healthy", f"近30次命中率 {recent_30}% 与验证期 {val_hit * 100:.0f}% 一致（差 {gap:.0f}pp）"
        return {
            "status": status,
            "validation_hit_rate": val_hit,
            "recent_30_hit_rate": recent_30,
            "recent_100_hit_rate": recent_100,
            "note": note,
        }

    @staticmethod
    def _proba_matrix(records: list) -> tuple[np.ndarray, np.ndarray]:
        """台账记录 → (y_true, y_proba)。概率为百分数，转为 0-1。列序 [down, range, up]。"""
        class_of = {"down": 0, "range": 1, "up": 2}
        y_true: list[int] = []
        proba: list[list[float]] = []
        for r in records:
            p = r.calibrated_probabilities or {}
            if not p or r.actual_class not in class_of:
                continue
            y_true.append(class_of[r.actual_class])
            proba.append([p.get("down", 0.0) / 100.0, p.get("range", 0.0) / 100.0, p.get("up", 0.0) / 100.0])
        if not proba:
            return np.array([], dtype=int), np.zeros((0, 3))
        return np.asarray(y_true, dtype=int), np.asarray(proba, dtype=float)

    def _calibration_drift(self, db, horizon: str, validation: dict, fund_id: int | None = None) -> dict:
        """Calibration Drift：近期 Brier/ECE/LogLoss vs 验证期。"""
        rows = self._recent_records(db, horizon, limit=100, fund_id=fund_id)
        y_true, proba = self._proba_matrix(rows)
        recent: dict = {}
        if len(y_true) >= DRIFT_MIN_CAL_RECORDS and proba.shape[1] == 3:
            cls = classification_metrics(y_true, np.argmax(proba, axis=1), proba)
            cal = calibration_metrics(y_true, proba)
            recent = {
                "brier_score": cls.get("brier_score"),
                "log_loss": cls.get("log_loss"),
                "ece": cal.get("ece"),
            }
        if not recent or validation.get("log_loss") is None:
            return {
                "status": "insufficient_data",
                "validation": {
                    "brier_score": validation.get("brier_score"),
                    "ece": validation.get("ece"),
                    "log_loss": validation.get("log_loss"),
                },
                "recent": recent or None,
                "note": f"台账样本不足 {DRIFT_MIN_CAL_RECORDS} 条，无法评估校准漂移",
            }

        status = "healthy"
        notes: list[str] = []
        for key in ("log_loss", "brier_score"):
            val = validation.get(key)
            rec = recent.get(key)
            if val is None or rec is None:
                continue
            rel = (rec - val) / val if val else 0.0
            if rel >= DRIFT_CAL_REL_DEGRADED:
                status = "degraded"
                notes.append(f"{key} 相对恶化 {rel * 100:.0f}%")
            elif rel >= DRIFT_CAL_REL_WARNING:
                status = max(status, "warning", key=lambda s: _STATUS_ORDER[s])
                notes.append(f"{key} 相对恶化 {rel * 100:.0f}%")
        val_ece = validation.get("ece")
        rec_ece = recent.get("ece")
        if val_ece is not None and rec_ece is not None:
            d = rec_ece - val_ece
            if d >= DRIFT_CAL_ECE_DEGRADED:
                status = "degraded"
                notes.append(f"ECE 增加 {d:.2f}")
            elif d >= DRIFT_CAL_ECE_WARNING:
                status = max(status, "warning", key=lambda s: _STATUS_ORDER[s])
                notes.append(f"ECE 增加 {d:.2f}")
        note = ("；".join(notes) + "。") if notes else "近期校准质量与验证期一致"
        return {
            "status": status,
            "validation": {
                "brier_score": validation.get("brier_score"),
                "ece": validation.get("ece"),
                "log_loss": validation.get("log_loss"),
            },
            "recent": recent,
            "note": note,
        }

    @staticmethod
    def _find_feature_value(record, col: str):
        """从台账特征快照（compact）查找特征值（跨层）。"""
        try:
            for layer in (record.feature_snapshot or {}).values():
                if isinstance(layer, dict) and col in layer:
                    info = layer[col]
                    if isinstance(info, dict):
                        return info.get("value")
        except Exception:  # noqa: BLE001
            return None
        return None

    def _feature_drift(self, db, horizon: str, meta: dict, fund_id: int | None = None) -> dict:
        """Feature Drift：主要特征近期均值 vs 训练期（标准化偏移，简单稳定统计）。"""
        train_mean = meta.get("feature_mean") or {}
        train_scale = meta.get("feature_scale") or {}
        importance = meta.get("feature_importance") or []
        top: list[str] = [
            imp.get("feature")
            for imp in importance[:DRIFT_TOP_FEATURES]
            if isinstance(imp, dict) and imp.get("feature")
        ]
        if not top:
            top = list(train_mean.keys())[:DRIFT_TOP_FEATURES]
        rows = self._recent_records(db, horizon, limit=100, fund_id=fund_id)
        if len(rows) < DRIFT_MIN_FEATURE_RECORDS:
            return {
                "status": "insufficient_data",
                "checked": len(top),
                "drifted_count": None,
                "drifted_features": [],
                "note": f"台账样本不足 {DRIFT_MIN_FEATURE_RECORDS} 条，无法评估特征漂移",
            }
        drifted: list[dict] = []
        checked = 0
        for col in top:
            vals = [v for r in rows if (v := self._find_feature_value(r, col)) is not None]
            if len(vals) < max(5, DRIFT_MIN_FEATURE_RECORDS // 2):
                continue
            train_m = train_mean.get(col)
            train_s = train_scale.get(col)
            if train_m is None or not train_s or train_s < 1e-9:
                continue
            checked += 1
            recent_mean = sum(vals) / len(vals)
            shift = abs(recent_mean - train_m) / train_s
            item = {
                "feature": col,
                "train_mean": round(float(train_m), 6),
                "recent_mean": round(float(recent_mean), 6),
                "train_std": round(float(train_s), 6),
                "shift_std": round(float(shift), 3),
            }
            if shift >= DRIFT_FEATURE_SHIFT:
                drifted.append(item)
        ratio = len(drifted) / checked if checked else 0.0
        if ratio >= DRIFT_FEATURE_DEGRADED_RATIO:
            status = "degraded"
        elif ratio >= DRIFT_FEATURE_WARNING_RATIO:
            status = "warning"
        else:
            status = "healthy"
        drifted.sort(key=lambda x: -x["shift_std"])
        note = (
            f"检查 {checked} 个主要特征，{len(drifted)} 个漂移（均值偏移 ≥{DRIFT_FEATURE_SHIFT} 个训练标准差）"
            if checked
            else "训练期特征统计缺失，无法评估特征漂移"
        )
        return {
            "status": status,
            "checked": checked,
            "drifted_count": len(drifted),
            "drifted_features": drifted[:10],
            "note": note,
        }

    @staticmethod
    def _overall_status(parts: list[dict]) -> str:
        """Overall：三通道中最差状态（insufficient_data 视为不可评估）。"""
        scores = [_STATUS_ORDER.get(p.get("status"), 0) for p in parts]
        if all(s == 0 for s in scores):
            return "insufficient_data"
        best = max(scores)
        return {3: "degraded", 2: "warning", 1: "healthy"}[best]

"""RetrainingManager：重训入口（手动/定时/表现触发）与模型健康度评估。

- 默认不自动频繁重训；重训保留 dataset/feature/model 版本快照（可重现）；
- 健康度：Champion 元数据 + 台账近 30/100 次真实命中率 vs 验证期表现
  → healthy / warning / degraded；
- 表现显著退化时给出重训建议（是否自动重训由配置决定）。
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.prediction.ledger import ledger_stats
from app.prediction.registry import ModelRegistry

log = get_logger("app.prediction")


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

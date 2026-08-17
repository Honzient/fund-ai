"""模型注册表：模型工件 + 元数据版本化管理 + Champion 机制。

- 版本号语义化：v{major}.{minor}（历史 v1 → 视作 v1.0）；
- 每次训练保存完整元数据：训练区间、特征/数据集版本、校准方法、完整指标、
  基线对比、状态、champion 标志 —— 重训不覆盖历史记录；
- 校准器与模型同版本存放；
- Champion：同一 horizon 下唯一 champion=True 的版本，由训练流程按 ModelScore 选出。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prediction.models import BaseModel

log = get_logger("app.prediction")

MODEL_FILENAME = "{version}_{horizon}.joblib"
CAL_FILENAME = "cal_{version}_{horizon}.joblib"
META_FILENAME = "{version}_{horizon}.meta.json"


def _parse_version(version: str) -> tuple[int, int]:
    text = (version or "").lstrip("v")
    parts = text.split(".")
    try:
        major = int(parts[0]) if parts[0] else 0
        minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        return major, minor
    except ValueError:
        return 0, 0


class ModelRegistry:
    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or get_settings().models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 版本

    def next_version(self, horizon: str) -> str:
        versions = [m.get("version", "v0") for m in self.list_models(horizon)]
        if not versions:
            return "v1.0"
        parsed = [_parse_version(v) for v in versions]
        major = max(p[0] for p in parsed)
        minors = [p[1] for p in parsed if p[0] == major]
        minor = max(minors) if minors else -1
        return f"v{major}.{minor + 1}"

    # ------------------------------------------------------------ 保存/加载

    def save(self, model: BaseModel, meta: dict, horizon: str, version: str) -> Path:
        model_path = self.models_dir / MODEL_FILENAME.format(version=version, horizon=horizon)
        meta_path = self.models_dir / META_FILENAME.format(version=version, horizon=horizon)
        joblib.dump(model, model_path)
        meta.setdefault("version", version)
        meta.setdefault("horizon", horizon)
        meta.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
        meta.setdefault("status", "active")
        meta.setdefault("champion", False)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2, default=str)
        log.info("模型已保存: %s (%s)", model_path.name, meta.get("model_name"))
        return model_path

    def save_calibrator(self, calibrator, horizon: str, version: str) -> Path:
        path = self.models_dir / CAL_FILENAME.format(version=version, horizon=horizon)
        calibrator.save(path)
        return path

    def load(self, version: str, horizon: str) -> tuple[Any, dict] | None:
        model_path = self.models_dir / MODEL_FILENAME.format(version=version, horizon=horizon)
        meta_path = self.models_dir / META_FILENAME.format(version=version, horizon=horizon)
        if not model_path.exists() or not meta_path.exists():
            return None
        try:
            model = joblib.load(model_path)
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
            return model, meta
        except Exception as exc:  # noqa: BLE001
            log.warning("模型加载失败 %s: %s", model_path, exc)
            return None

    def load_calibrator(self, version: str, horizon: str):
        from app.prediction.calibration import ProbabilityCalibrator

        path = self.models_dir / CAL_FILENAME.format(version=version, horizon=horizon)
        if not path.exists():
            return None
        try:
            return ProbabilityCalibrator.load(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("校准器加载失败 %s: %s", path, exc)
            return None

    def get_champion(self, horizon: str) -> dict | None:
        for meta in self.list_models(horizon):
            if meta.get("champion"):
                return meta
        return None

    # ------------------------------------------------------------ 元数据

    def list_models(self, horizon: str | None = None) -> list[dict]:
        metas: list[dict] = []
        for meta_path in sorted(self.models_dir.glob("*.meta.json"), reverse=True):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:  # noqa: BLE001
                continue
            if horizon and meta.get("horizon") != horizon:
                continue
            metas.append(meta)
        metas.sort(key=lambda m: _parse_version(m.get("version", "v0")), reverse=True)
        return metas

    def _update_meta(self, horizon: str, version: str, **fields) -> None:
        meta_path = self.models_dir / META_FILENAME.format(version=version, horizon=horizon)
        if not meta_path.exists():
            return
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        meta.update(fields)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2, default=str)

    def set_champion(self, horizon: str, version: str) -> None:
        """version 成为该 horizon 的 champion；其余版本退役。"""
        for meta in self.list_models(horizon):
            v = meta.get("version")
            if v == version:
                self._update_meta(horizon, v, champion=True, status="active")
            else:
                self._update_meta(horizon, v, champion=False, status="retired")
        log.info("Champion 已更新: %s/%s", horizon, version)

    def set_status(self, horizon: str, version: str, status: str) -> None:
        self._update_meta(horizon, version, status=status)

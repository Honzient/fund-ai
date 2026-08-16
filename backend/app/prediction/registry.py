"""模型注册表：模型工件 + 元数据版本化管理。

模型文件: storage/models/{version}_{horizon}.joblib
元数据:   storage/models/{version}_{horizon}.meta.json
重新训练生成新版本，不影响历史分析结果。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prediction.models import BaseModel

log = get_logger("app.prediction")

MODEL_FILENAME = "{version}_{horizon}.joblib"
META_FILENAME = "{version}_{horizon}.meta.json"


class ModelRegistry:
    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or get_settings().models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def next_version(self) -> str:
        versions: set[int] = set()
        for meta_path in self.models_dir.glob("*.meta.json"):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
                version = str(meta.get("version", ""))
                if version.startswith("v"):
                    versions.add(int(version[1:]))
            except Exception:  # noqa: BLE001
                continue
        return f"v{max(versions) + 1 if versions else 1}"

    def save(self, model: BaseModel, meta: dict, horizon: str, version: str) -> Path:
        model_path = self.models_dir / MODEL_FILENAME.format(version=version, horizon=horizon)
        meta_path = self.models_dir / META_FILENAME.format(version=version, horizon=horizon)
        joblib.dump(model, model_path)
        meta.setdefault("version", version)
        meta.setdefault("horizon", horizon)
        meta.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2, default=str)
        log.info("模型已保存: %s (%s)", model_path.name, model.name)
        return model_path

    def load(self, version: str, horizon: str) -> tuple[BaseModel, dict] | None:
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

    def latest(self, horizon: str) -> tuple[BaseModel, dict] | None:
        metas = self.list_models(horizon)
        if not metas:
            return None
        latest_meta = metas[0]  # 已按版本倒序
        return self.load(latest_meta["version"], horizon)

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
        metas.sort(key=lambda m: m.get("version", ""), reverse=True)
        return metas

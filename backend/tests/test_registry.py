"""模型注册表测试：语义版本、不覆盖历史、Champion 迁移、校准器同版本。"""
import numpy as np
import pytest

from app.prediction.calibration import ProbabilityCalibrator
from app.prediction.models import get_model
from app.prediction.registry import ModelRegistry, _parse_version


@pytest.fixture()
def registry():
    from app.core.config import get_settings

    r = ModelRegistry(get_settings().models_dir)
    for meta in r.list_models():
        for suffix in (".joblib", ".meta.json"):
            path = r.models_dir / meta["version"]
        # 清理旧文件，保证测试隔离
    for path in r.models_dir.glob("v*.joblib"):
        path.unlink(missing_ok=True)
    for path in r.models_dir.glob("v*.meta.json"):
        path.unlink(missing_ok=True)
    for path in r.models_dir.glob("cal_*.joblib"):
        path.unlink(missing_ok=True)
    return r


def test_parse_version():
    assert _parse_version("v1") == (1, 0)
    assert _parse_version("v2.3") == (2, 3)
    assert _parse_version("v0.2.3") == (0, 2)
    assert _parse_version("bogus") == (0, 0)


def test_semantic_version_increment(registry):
    assert registry.next_version("short") == "v1.0"
    registry.save(get_model("logistic"), {"model_name": "logistic", "horizon": "short"}, "short", "v1.0")
    assert registry.next_version("short") == "v1.1"
    registry.save(get_model("logistic"), {"model_name": "logistic", "horizon": "short"}, "short", "v1.1")
    assert registry.next_version("short") == "v1.2"
    # 其他 horizon 独立
    assert registry.next_version("medium") == "v1.0"


def test_history_not_overwritten(registry):
    registry.save(get_model("logistic"), {"model_name": "logistic"}, "short", "v1.0")
    registry.save(get_model("random_forest"), {"model_name": "random_forest"}, "short", "v2.0")
    metas = registry.list_models("short")
    assert len(metas) == 2
    assert metas[0]["version"] == "v2.0"
    assert metas[1]["version"] == "v1.0"
    # 旧版本仍可加载
    loaded = registry.load("v1.0", "short")
    assert loaded is not None


def test_champion_transition(registry):
    registry.save(get_model("logistic"), {"model_name": "logistic", "champion": False}, "short", "v1.0")
    registry.save(get_model("random_forest"), {"model_name": "random_forest", "champion": False}, "short", "v2.0")
    registry.set_champion("short", "v2.0")
    champion = registry.get_champion("short")
    assert champion["version"] == "v2.0"
    assert champion["status"] == "active"
    v1 = next(m for m in registry.list_models("short") if m["version"] == "v1.0")
    assert v1["status"] == "retired"
    # 换 Champion：旧 champion 退役
    registry.set_champion("short", "v1.0")
    v2 = next(m for m in registry.list_models("short") if m["version"] == "v2.0")
    assert v2["status"] == "retired"
    assert registry.get_champion("short")["version"] == "v1.0"


def test_calibrator_saved_with_version(registry):
    rng = np.random.default_rng(3)
    y = rng.integers(0, 3, size=400)
    p = rng.dirichlet([1, 1, 1], size=400)
    cal = ProbabilityCalibrator(method="sigmoid").fit(y, p)
    registry.save(get_model("logistic"), {"model_name": "logistic"}, "short", "v1.0")
    registry.save_calibrator(cal, "short", "v1.0")
    loaded_cal = registry.load_calibrator("v1.0", "short")
    assert loaded_cal is not None
    assert loaded_cal.method == cal.method
    # 不存在的版本 → None
    assert registry.load_calibrator("v9.9", "short") is None

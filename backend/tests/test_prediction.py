"""预测引擎测试：概率输出 / 训练注册 / 回测 / 统计基线。"""
import numpy as np
import pandas as pd
import pytest

from app.prediction import PredictionEngine, engine as engine_module


@pytest.fixture()
def engine():
    return PredictionEngine()


def test_baseline_probabilities_sum_to_100(engine):
    df = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=100), "nav": 1 + np.arange(100) * 0.01})
    result = engine._baseline_predict(df, "short")
    probs = result["probabilities"]
    assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100.0, abs=0.5)
    assert result["confidence"] in ("low", "medium")


def test_predict_insufficient_data_returns_flat(engine, monkeypatch):
    def _no_history(code, years=4.0):
        return None

    monkeypatch.setattr(engine_module, "_load_fund_history", _no_history)
    result = engine.predict("000000", "short")
    assert result["probabilities"]["up"] == pytest.approx(33.3, abs=0.5)
    assert result["confidence"] == "low"
    assert result["model_version"] == "baseline"


def _synthetic_funds(n_funds=6, n_days=500, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    funds: dict[str, pd.DataFrame] = {}
    for i in range(n_funds):
        nav = 1.0 * np.exp(np.cumsum(rng.normal(0.0004 + i * 0.00005, 0.012, n_days)))
        funds[f"T{i:03d}"] = pd.DataFrame({"date": dates, "nav": nav})
    market = pd.Series(
        3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n_days))),
        index=pd.Index(dates, name="date"),
    )
    return funds, market


def test_train_and_register(engine, monkeypatch):
    """合成数据训练 → 模型注册表出现新版本。"""
    funds, market = _synthetic_funds()
    monkeypatch.setattr(engine_module, "_load_all_histories", lambda years=4.0: (funds, market))
    meta = engine.train("short")
    assert meta is not None
    assert meta["version"].startswith("v")
    assert meta["samples"] > 100
    assert "accuracy" in meta["metrics"]
    assert meta["feature_importance"]
    assert meta["validation"] == "TimeSeriesSplit（时间顺序，无随机切分）"
    models = engine.registry.list_models("short")
    assert any(m["version"] == meta["version"] for m in models)


def test_backtest_available(engine, monkeypatch):
    funds, market = _synthetic_funds(n_funds=4, n_days=900)
    monkeypatch.setattr(engine_module, "_load_all_histories", lambda years=4.0: (funds, market))
    result = engine.backtest("short")
    assert result is not None
    if result.get("available"):
        m = result["metrics"]
        assert 0 <= m["direction_accuracy"] <= 100
        assert "历史回测不代表未来表现" in result["disclaimer"]
        assert result["note"].startswith("Walk-Forward")

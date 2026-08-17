"""预测引擎 v0.2 测试：概率输出 / 训练注册 / 校准 / 回测 / 统计基线 / Purged 切分。"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.prediction import PredictionEngine


@pytest.fixture()
def engine():
    return PredictionEngine()


def _synthetic_funds(n_funds=6, n_days=500, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    funds: dict[str, pd.DataFrame] = {}
    for i in range(n_funds):
        nav = 1.0 * np.exp(np.cumsum(rng.normal(0.0004 + i * 0.00005, 0.012, n_days)))
        funds[f"T{i:03d}"] = pd.DataFrame({"date": dates, "nav": nav})
    market = pd.Series(
        3000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n_days))),
        index=pd.DatetimeIndex(dates, name="date"),
    )
    return funds, market


@pytest.fixture()
def synthetic_store(monkeypatch):
    """用合成数据替换 FeatureStore 的 DB 加载（无数据库依赖）。"""
    from app.prediction import feature_store as fs_module

    funds, market = _synthetic_funds()

    def fake_load_fund_histories(self, years=4.0):
        return {k: v for k, v in funds.items()}

    def fake_load_market_series(self, years=4.0):
        return market

    def fake_macro(self):
        return {}

    def fake_news(self):
        return pd.Series(dtype=float), pd.Series(dtype=float)

    def fake_policy(self):
        e = pd.Series(dtype=float)
        return e, e, e

    def fake_industry(self):
        return {}

    def fake_static(self, code, as_of=None):
        return {
            "fund_size": 100.0, "fund_age_years": 8.0,
            "top10_concentration": 50.0, "industry_hhi": 0.2,
            "industries": {"测试行业": 50.0}, "top_industry": "测试行业",
            "top_industry_weight": 50.0, "holdings_report_date": None,
        }

    def fake_holdings(self, code):
        # 两期持仓快照（Point-in-Time：训练按 available_at 截断）
        return [
            {
                "report_date": date(2022, 1, 31), "available_at": date(2022, 2, 28),
                "top10_concentration": 45.0, "industry_hhi": 0.15,
                "industries": {"测试行业": 45.0}, "top_industry": "测试行业",
                "top_industry_weight": 45.0,
            },
            {
                "report_date": date(2023, 6, 30), "available_at": date(2023, 8, 31),
                "top10_concentration": 55.0, "industry_hhi": 0.25,
                "industries": {"测试行业": 55.0}, "top_industry": "测试行业",
                "top_industry_weight": 55.0,
            },
        ]

    def fake_meta(self, code):
        return {"establish_date": date(2015, 1, 1)}

    monkeypatch.setattr(fs_module.FeatureStore, "_load_fund_histories", fake_load_fund_histories)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_market_series", fake_load_market_series)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_macro_series", fake_macro)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_news_daily", fake_news)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_policy_daily", fake_policy)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_industry_daily", fake_industry)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_fund_static", fake_static)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_fund_holdings", fake_holdings)
    monkeypatch.setattr(fs_module.FeatureStore, "_load_fund_meta", fake_meta)
    return funds


def test_baseline_probabilities_sum_to_100(engine):
    df = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=100), "nav": 1 + np.arange(100) * 0.01})
    result = engine._baseline_predict(df, "short")
    probs = result["probabilities"]
    assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100.0, abs=0.5)
    assert result["confidence"] in ("low", "medium")
    assert result["calibrated_probabilities"] == probs


def test_predict_without_champion_returns_baseline(engine, monkeypatch):
    """模型未就绪时 predict 绝不训练、绝不留空：返回统计基线 + 明确标注。"""
    funds = _synthetic_funds(n_funds=2, n_days=200)[0]
    monkeypatch.setattr(engine.store, "_load_fund_histories", lambda years=4.0: funds)
    from app.prediction.registry import ModelRegistry

    monkeypatch.setattr(engine, "registry", ModelRegistry())
    result = engine.predict("T000", "short")
    assert result["model_version"] == "baseline"
    # 两种合法降级路径：模型未就绪 / 历史数据不足（均明确标注，不伪造）
    note = result.get("note") or ""
    assert ("模型未就绪" in note) or ("历史数据不足" in note)
    probs = result["probabilities"]
    assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100.0, abs=0.5)
    assert result["raw_probabilities"]
    assert result["calibrated_probabilities"]


def test_train_and_register(engine, synthetic_store):
    """合成数据训练 → Champion 注册 + 完整元数据 + 基线对比。"""
    meta = engine.train("short")
    assert meta is not None
    assert meta["version"].startswith("v")
    assert meta["samples"] > 100
    metrics = meta["metrics"]
    for key in ("brier_score", "log_loss", "balanced_accuracy", "hit_rate", "model_score"):
        assert key in metrics
    assert meta["calibration_method"] in ("isotonic", "sigmoid", "uncalibrated")
    assert meta["feature_version"]
    assert meta["dataset_version"]
    assert "momentum" in meta["baseline_comparison"] or "majority" in meta["baseline_comparison"]
    assert meta["validation"].startswith("PurgedTimeSeriesSplit")
    champion = engine.registry.get_champion("short")
    assert champion is not None
    assert champion["champion"] is True
    assert champion["version"] == meta["version"]
    cal = engine.registry.load_calibrator(meta["version"], "short")
    assert cal is not None


def test_predict_with_champion_outputs_calibrated(engine, synthetic_store):
    engine.train("short")
    result = engine.predict("T000", "short")
    assert result["model_version"].startswith("v")
    assert result["champion"] is True
    probs = result["calibrated_probabilities"]
    assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100.0, abs=0.5)
    assert result["raw_probabilities"]
    assert result["probabilities"] == probs
    assert result["predicted_class"] in ("up", "range", "down")
    assert result["calibration_method"] in ("isotonic", "sigmoid", "uncalibrated")
    assert result["feature_snapshot"]
    assert result["market_snapshot"] is not None


def test_backtest_with_baselines(engine, synthetic_store):
    result = engine.backtest("short", "latest")
    assert result is not None
    if result.get("available"):
        m = result["metrics"]
        assert 0 <= m["accuracy"] <= 100
        assert "momentum" in result["baselines"]
        assert "majority" in result["baselines"]
        assert "历史回测不代表未来表现" in result["disclaimer"]
        assert result["note"].startswith("Walk-Forward")


def test_purged_split_no_label_overlap():
    from app.prediction.splits import PurgedTimeSeriesSplit, assert_no_label_overlap

    dates = np.array(pd.bdate_range("2023-01-01", periods=300).to_numpy())
    splitter = PurgedTimeSeriesSplit(dates, n_splits=4, horizon=20)
    splits = list(splitter.split())
    assert len(splits) >= 3
    assert assert_no_label_overlap(dates, splits, horizon=20)


def test_purged_split_embargo():
    from app.prediction.splits import PurgedTimeSeriesSplit

    dates = np.array(pd.bdate_range("2023-01-01", periods=200).to_numpy())
    splitter = PurgedTimeSeriesSplit(dates, n_splits=3, horizon=10, embargo=10, purge=9)
    for train_idx, test_idx in splitter.split():
        train_dates = dates[train_idx]
        test_dates = dates[test_idx]
        assert train_dates.max() < test_dates.min()
        gap = np.sum(dates <= test_dates.min()) - np.sum(dates <= train_dates.max())
        assert gap >= 18


def test_calibration_fallback_when_insufficient():
    from app.prediction.calibration import ProbabilityCalibrator

    rng = np.random.default_rng(7)
    y = rng.integers(0, 3, size=50)
    p = rng.dirichlet([1, 1, 1], size=50)
    cal = ProbabilityCalibrator(method="isotonic").fit(y, p)
    assert cal.method == "uncalibrated"
    out = cal.predict(p)
    assert np.allclose(out.sum(axis=1), 1.0)


def test_calibration_output_normalized():
    from app.prediction.calibration import ProbabilityCalibrator

    rng = np.random.default_rng(8)
    n = 400
    y = rng.integers(0, 3, size=n)
    p = rng.dirichlet([1, 1, 1], size=n)
    cal = ProbabilityCalibrator(method="sigmoid").fit(y, p)
    out = cal.predict(p)
    assert out.shape == (n, 3)
    assert np.all(out >= 0) and np.all(out <= 1)
    assert np.allclose(out.sum(axis=1), 1.0, atol=1e-6)


# ---------------------------------------------------------------- Champion 选择（v0.3）

def test_champion_selected_by_calibrated_score():
    """Champion 按校准后 ModelScore 选择：模型 A raw 好但校准差，模型 B raw 稍差但校准更好 → 选 B。"""
    from app.prediction.engine import PredictionEngine

    results = {
        "logistic": {"metrics": {"model_score": 90.0}, "calibrated_metrics": {"model_score": 40.0}},
        "random_forest": {"metrics": {"model_score": 85.0}, "calibrated_metrics": {"model_score": 88.0}},
    }
    assert PredictionEngine._pick_champion(results) == "random_forest"


def test_champion_falls_back_to_raw_when_uncalibrated():
    """校准不可用（uncalibrated）时回退未校准分数选择。"""
    from app.prediction.engine import PredictionEngine

    results = {
        "logistic": {"metrics": {"model_score": 90.0}},
        "random_forest": {"metrics": {"model_score": 85.0}, "calibrated_metrics": {"model_score": 70.0}},
    }
    assert PredictionEngine._pick_champion(results) == "logistic"


def test_evaluate_candidates_reports_calibrated_metrics(engine, synthetic_store):
    """候选评测输出校准后指标，Champion 与「校准后分数最高（不可用时回退 raw）」一致。"""
    result = engine.evaluate_candidates("short")
    assert result is not None
    for name in ("logistic", "random_forest"):
        cand = result["candidates"][name]
        assert "calibration" in cand
        if cand["calibration"].get("calibrated"):
            assert cand["calibrated_metrics"]["model_score"] is not None
            assert "ece" in cand["calibrated_metrics"]
        else:
            assert cand["calibration"]["method"] == "uncalibrated"
            assert "calibrated_metrics" not in cand

    def pick_score(name):
        cand = result["candidates"][name]
        cal = cand.get("calibrated_metrics") or {}
        if cal.get("model_score") is not None:
            return cal["model_score"]
        return cand["metrics"]["model_score"]

    expected = max(("logistic", "random_forest"), key=pick_score)
    assert result["champion"] == expected


def test_train_saves_calibrator_of_calibrated_champion(engine, synthetic_store):
    """train 复用候选评测的校准器与校准后指标注册 Champion。"""
    eval_result = engine.evaluate_candidates("short")
    assert eval_result is not None
    champion = eval_result["champion"]
    champion_res = eval_result["candidates"][champion]
    meta = engine.train("short")
    assert meta is not None
    assert meta["calibration_method"] == champion_res["calibration"]["method"]
    cal = champion_res.get("calibrated_metrics")
    if cal is not None:
        assert meta["calibrated_metrics"]["model_score"] == cal["model_score"]
        assert meta["calibrated_metrics"]["ece"] == cal["ece"]
    else:
        # 校准不可用：meta 的校准后指标回退为未校准指标
        assert meta["calibrated_metrics"]["model_score"] == meta["metrics"]["model_score"]
    loaded = engine.registry.load_calibrator(meta["version"], "short")
    assert loaded is not None
    assert loaded.method == meta["calibration_method"]

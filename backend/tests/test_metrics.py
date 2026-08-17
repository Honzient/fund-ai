"""指标套件测试：完整指标体系 + ModelScore 边界。"""
import numpy as np
import pytest

from app.prediction.metrics import (
    calibration_metrics,
    evaluate_model,
    model_score,
)


def test_perfect_predictions():
    y_true = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2] * 20)
    y_pred = y_true.copy()
    y_proba = np.eye(3)[y_true]
    metrics = evaluate_model(y_true, y_pred, y_proba)
    assert metrics["accuracy"] == pytest.approx(1.0)
    assert metrics["brier_score"] == pytest.approx(0.0, abs=1e-3)
    assert metrics["log_loss"] < 0.05
    assert metrics["ece"] == pytest.approx(0.0, abs=0.01)
    assert metrics["hit_rate"] == pytest.approx(1.0)
    assert metrics["model_score"] > 90


def test_random_predictions_metrics_in_range():
    rng = np.random.default_rng(5)
    n = 300
    y_true = rng.integers(0, 3, size=n)
    y_pred = rng.integers(0, 3, size=n)
    y_proba = rng.dirichlet([1, 1, 1], size=n)
    metrics = evaluate_model(y_true, y_pred, y_proba)
    for key in ("accuracy", "balanced_accuracy", "brier_score", "log_loss", "ece", "hit_rate"):
        assert metrics[key] is not None
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["model_score"] <= 100
    assert metrics["brier_score"] > 0


def test_model_score_bounds_and_ordering():
    good = {"brier_score": 0.5, "log_loss": 0.6, "balanced_accuracy": 0.55, "hit_rate": 0.55, "ece": 0.1}
    bad = {"brier_score": 1.6, "log_loss": 1.2, "balanced_accuracy": 0.35, "hit_rate": 0.35, "ece": 0.4}
    assert model_score(good) > model_score(bad)
    assert 0 <= model_score(bad) <= 100


def test_calibration_metrics_shape():
    rng = np.random.default_rng(6)
    n = 200
    y_true = rng.integers(0, 3, size=n)
    y_proba = rng.dirichlet([1, 1, 1], size=n)
    result = calibration_metrics(y_true, y_proba)
    assert 0 <= result["ece"] <= 1
    assert result["mce"] >= 0
    assert len(result["bins"]) > 0
    for b in result["bins"]:
        assert 0 <= b["avg_probability"] <= 1
        assert 0 <= b["avg_actual"] <= 1

"""模型漂移监测测试（v0.3）：Performance / Calibration / Feature 三通道。"""
from datetime import date, datetime, timezone

from app.models import Fund
from app.prediction.ledger import PredictionRecord
from app.prediction.retraining import RetrainingManager

_CONF = timezone.utc

META = {
    "model_name": "logistic",
    "version": "v1.0.0",
    "calibrated_metrics": {
        "hit_rate": 0.60, "brier_score": 0.60, "log_loss": 1.00, "ece": 0.10, "model_score": 60.0,
    },
    "metrics": {
        "hit_rate": 0.60, "brier_score": 0.60, "log_loss": 1.00, "ece": 0.10, "model_score": 60.0,
    },
    "feature_mean": {"ret_20": 0.001, "rsi14": 50.0, "vol_20": 0.012, "mdd_60": -0.05},
    "feature_scale": {"ret_20": 0.012, "rsi14": 10.0, "vol_20": 0.005, "mdd_60": 0.10},
    "feature_importance": [
        {"feature": "ret_20", "importance": 0.3},
        {"feature": "rsi14", "importance": 0.2},
        {"feature": "vol_20", "importance": 0.1},
        {"feature": "mdd_60", "importance": 0.1},
    ],
}
# 只检查 3 个主要特征（用于 warning 边界）
META3 = {**META, "feature_importance": META["feature_importance"][:3]}


def _manager():
    return RetrainingManager(object())


def _fund(db, code: str) -> Fund:
    fund = Fund(
        fund_code=code, fund_name=code, fund_type="混合型",
        establish_date=date(2019, 1, 1), source="test",
    )
    db.add(fund)
    db.flush()
    return fund


def _tech(ret20=0.001, rsi=50.0, vol=0.012, mdd=-0.05):
    return {
        "technical": {
            "ret_20": {"value": ret20, "quality": "high"},
            "rsi14": {"value": rsi, "quality": "high"},
            "vol_20": {"value": vol, "quality": "high"},
            "mdd_60": {"value": mdd, "quality": "high"},
        }
    }


def _rec(db, fund_id: int, day: int, cls, actual, probs, tech=None, horizon: str = "short"):
    db.add(
        PredictionRecord(
            fund_id=fund_id,
            prediction_date=date(2024, 1, day),
            horizon=horizon,
            horizon_days=5,
            model_name="logistic",
            model_version="v1.0.0",
            calibrated=True,
            calibration_method="isotonic",
            predicted_class=cls,
            actual_class=actual,
            calibrated_probabilities=probs,
            confidence="high",
            confidence_score=0.8,
            feature_snapshot=tech,
            actual_return=1.0,
            evaluated_at=datetime(2024, 3, 1, tzinfo=_CONF),
        )
    )


_GOOD_UP = {"up": 95.0, "range": 2.5, "down": 2.5}
_GOOD_DOWN = {"down": 95.0, "range": 2.5, "up": 2.5}
_BAD_PROBS = {"up": 20.0, "range": 40.0, "down": 40.0}


def test_drift_no_model(db):
    result = _manager()._drift_for(db, "short", None)  # noqa: SLF001
    assert result["champion"] is None
    assert result["overall"] == "no_model"


def test_drift_healthy(db):
    """三通道均健康：近期表现/校准/特征与训练期一致。"""
    fund = _fund(db, "DRIFT01")
    db.flush()
    for i in range(18):
        _rec(db, fund.id, i + 1, "up", "up", _GOOD_UP, _tech())
    for i in range(12):
        _rec(db, fund.id, i + 19, "down", "down", _GOOD_DOWN, _tech())
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    assert result["performance"]["status"] == "healthy"
    assert result["calibration"]["status"] == "healthy"
    assert result["feature_drift"]["status"] == "healthy"
    assert result["overall"] == "healthy"


def test_drift_performance_degraded(db):
    """近期命中率远低于验证期 → Performance degraded。"""
    fund = _fund(db, "DRIFT02")
    db.flush()
    for i in range(30):
        _rec(db, fund.id, i + 1, "up", "down", _GOOD_UP, _tech())
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    perf = result["performance"]
    assert perf["status"] == "degraded"
    assert perf["recent_30_hit_rate"] == 0.0
    assert result["overall"] == "degraded"


def test_drift_performance_warning(db):
    """命中率差 10pp（≥8 <15）→ Performance warning。"""
    fund = _fund(db, "DRIFT07")
    db.flush()
    for i in range(15):
        _rec(db, fund.id, i + 1, "up", "up", _GOOD_UP, _tech())
    for i in range(15):
        _rec(db, fund.id, i + 16, "up", "down", _GOOD_UP, _tech())
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    assert result["performance"]["status"] == "warning"
    assert result["performance"]["recent_30_hit_rate"] == 50.0


def test_drift_calibration_degraded(db):
    """预测命中但概率严重失真（正确类仅 20%）→ Calibration degraded。"""
    fund = _fund(db, "DRIFT03")
    db.flush()
    for i in range(30):
        _rec(db, fund.id, i + 1, "up", "up", _BAD_PROBS, _tech())
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    cal = result["calibration"]
    assert cal["status"] == "degraded"
    assert cal["recent"]["log_loss"] > 1.5
    # 命中率 100% → Performance 正常，Overall 由校准漂移决定
    assert result["performance"]["status"] == "healthy"
    assert result["overall"] == "degraded"


def test_drift_feature_warning(db):
    """1/3 主要特征漂移（≥30%）→ Feature warning。"""
    fund = _fund(db, "DRIFT04")
    db.flush()
    for i in range(30):
        _rec(db, fund.id, i + 1, "up", "up", _GOOD_UP, _tech(ret20=0.05))  # ret_20 大幅偏移
    db.commit()

    result = _manager()._drift_for(db, "short", META3, fund_id=fund.id)  # noqa: SLF001
    feat = result["feature_drift"]
    assert feat["status"] == "warning"
    assert feat["drifted_count"] == 1
    assert feat["drifted_features"][0]["feature"] == "ret_20"
    assert feat["drifted_features"][0]["shift_std"] > 2.0


def test_drift_feature_degraded(db):
    """2/4 主要特征漂移（≥50%）→ Feature degraded。"""
    fund = _fund(db, "DRIFT05")
    db.flush()
    for i in range(30):
        _rec(db, fund.id, i + 1, "up", "up", _GOOD_UP, _tech(ret20=0.05, rsi=55.0))
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    feat = result["feature_drift"]
    assert feat["status"] == "degraded"
    assert feat["drifted_count"] == 2
    # rsi14 偏移恰好 0.5 个训练标准差 → 计入漂移（边界）
    assert any(f["feature"] == "rsi14" and f["shift_std"] == 0.5 for f in feat["drifted_features"])


def test_drift_insufficient(db):
    """台账无记录 → 三通道 insufficient_data，Overall insufficient_data。"""
    fund = _fund(db, "DRIFT06")
    db.commit()

    result = _manager()._drift_for(db, "short", META, fund_id=fund.id)  # noqa: SLF001
    assert result["performance"]["status"] == "insufficient_data"
    assert result["calibration"]["status"] == "insufficient_data"
    assert result["feature_drift"]["status"] == "insufficient_data"
    assert result["overall"] == "insufficient_data"


def test_drift_horizon_isolation(db):
    """不同 horizon 的记录互不影响。"""
    f_short = _fund(db, "DRIFT08")
    f_long = _fund(db, "DRIFT09")
    db.flush()
    for i in range(30):
        _rec(db, f_short.id, i + 1, "up", "up", _GOOD_UP, _tech())
    for i in range(30):
        _rec(db, f_long.id, i + 1, "up", "down", _GOOD_UP, _tech(), horizon="long")
    db.commit()

    short_result = _manager()._drift_for(db, "short", META, fund_id=f_short.id)  # noqa: SLF001
    long_result = _manager()._drift_for(db, "long", META, fund_id=f_long.id)  # noqa: SLF001
    assert short_result["performance"]["status"] == "healthy"
    assert long_result["performance"]["status"] == "degraded"

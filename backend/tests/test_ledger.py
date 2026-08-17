"""预测台账（Prediction Ledger）测试：记录 → 去重 → 评价 → 历史 → 统计。"""
from datetime import date, timedelta

import pytest

from app.models import Fund, FundDailyData
from app.prediction.ledger import (
    PredictionRecord,
    evaluate_pending,
    ledger_history,
    ledger_stats,
    record_prediction,
)


def _make_fund(db, code: str):
    fund = Fund(fund_code=code, fund_name=f"测试基金{code}", fund_type="混合型", source="mock")
    db.add(fund)
    db.commit()
    db.refresh(fund)
    start = date(2025, 1, 2)
    nav = 1.0
    for i in range(120):
        nav *= 1 + (0.01 if i % 3 == 0 else -0.002)
        db.add(FundDailyData(fund_id=fund.id, date=start + timedelta(days=i), nav=round(nav, 4), source="mock"))
    db.commit()
    return fund


def test_record_and_dedupe(db):
    fund = _make_fund(db, "T901")
    payload = {
        "horizon": "short",
        "horizon_days": 5,
        "data_as_of": date(2025, 1, 2),
        "model_name": "logistic",
        "model_version": "v1.0",
        "calibrated": True,
        "calibration_method": "isotonic",
        "raw_probabilities": {"up": 40.0, "range": 30.0, "down": 30.0},
        "calibrated_probabilities": {"up": 42.0, "range": 30.0, "down": 28.0},
        "predicted_class": "up",
        "confidence": "medium",
        "confidence_score": 0.5,
        "feature_snapshot": {"technical": {"rsi14": {"value": 55.0, "quality": "high"}}},
        "market_snapshot": {"regime": {"label": "中性"}},
    }
    r1 = record_prediction(db, fund.id, payload)
    r2 = record_prediction(db, fund.id, payload)  # 同日同周期去重
    assert r1.id == r2.id
    assert db.query(PredictionRecord).filter(PredictionRecord.fund_id == fund.id).count() == 1


def test_evaluate_pending(db):
    fund = _make_fund(db, "T902")
    # 预测日选在数据中部，前向 horizon 已有净值
    pred_date = date(2025, 1, 10)
    record_prediction(
        db, fund.id,
        {
            "horizon": "short", "horizon_days": 5, "data_as_of": pred_date,
            "predicted_class": "up", "calibrated_probabilities": {"up": 60.0, "range": 25.0, "down": 15.0},
        },
    )
    result = evaluate_pending(db)
    assert result["evaluated"] >= 1
    row = db.query(PredictionRecord).filter(PredictionRecord.fund_id == fund.id).first()
    assert row.actual_class in ("up", "range", "down")
    assert row.actual_return is not None
    assert row.evaluated_at is not None
    # 再跑一次：该记录不再重复评价（evaluated_at 不变）
    first_eval = row.evaluated_at
    evaluate_pending(db)
    db.refresh(row)
    assert row.evaluated_at == first_eval


def test_ledger_history_and_stats(db):
    fund = _make_fund(db, "T903")
    for i in range(3):
        pred_date = date(2025, 1, 2) + timedelta(days=i)
        record_prediction(
            db, fund.id,
            {
                "horizon": "short", "horizon_days": 5, "data_as_of": pred_date,
                "predicted_class": "up" if i % 2 == 0 else "down",
            },
        )
    history = ledger_history(db, fund.id)
    assert len(history) == 3
    assert history[0]["prediction_date"]
    stats = ledger_stats(db, fund.id)
    assert "last_30" in stats["overall"]

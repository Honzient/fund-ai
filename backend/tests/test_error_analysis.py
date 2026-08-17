"""错误环境分析测试（v0.3）：模型在什么环境下更容易预测错误。"""
from datetime import date, datetime, timezone

from app.models import Fund
from app.prediction.ledger import PredictionRecord, error_analysis

_CONF = timezone.utc


def _add_fund(db, code: str, name: str, fund_type: str = "混合型") -> Fund:
    fund = Fund(
        fund_code=code, fund_name=name, fund_type=fund_type,
        establish_date=date(2019, 1, 1), source="test",
    )
    db.add(fund)
    db.flush()
    return fund


def _tech(rsi, vol, mdd):
    return {
        "technical": {
            "rsi14": {"value": rsi, "quality": "high"},
            "vol_20": {"value": vol, "quality": "high"},
            "mdd_60": {"value": mdd, "quality": "high"},
        }
    }


def _market(label):
    return {"regime": {"label": label, "score": 60.0, "drivers": []}, "breadth": 50.0, "generated_at": "2024-01-05"}


def _add_rec(db, fund_id: int, day: int, cls, actual, conf, market_label, tech=None, horizon: str = "short"):
    db.add(
        PredictionRecord(
            fund_id=fund_id,
            prediction_date=date(2024, 1, day),
            horizon=horizon,
            horizon_days=5,
            model_name="test-model",
            model_version="v0.3.0",
            calibrated=True,
            calibration_method="isotonic",
            predicted_class=cls,
            confidence=conf,
            confidence_score=None,
            feature_snapshot=tech,
            market_snapshot=_market(market_label) if market_label else None,
            actual_return=1.0,
            actual_class=actual,
            evaluated_at=datetime(2024, 3, 1, tzinfo=_CONF),
        )
    )


def _envs(result) -> dict:
    return {e["dimension"]: {b["bucket"]: b for b in e["buckets"]} for e in result["environments"]}


def test_error_analysis_empty(db):
    """无数据：sample_count=0，所有环境维度为空。"""
    fund = _add_fund(db, "ERRANA00", "错误分析空基金")
    db.commit()
    result = error_analysis(db, fund_id=fund.id)
    assert result["sample_count"] == 0
    assert all(e["buckets"] == [] for e in result["environments"])


def test_error_analysis_normal(db):
    """正常数据：多环境下命中率/错误率统计（手算期望值）。"""
    fund = _add_fund(db, "ERRANA01", "错误分析样本基金", fund_type="混合型-偏股")
    db.flush()
    fid = fund.id
    _add_rec(db, fid, 1, "up", "up", "high", "中性偏多", _tech(75, 0.03, -0.20))      # bull 命中
    _add_rec(db, fid, 2, "up", "down", "high", "中性偏多", _tech(80, 0.025, -0.25))    # bull 错误
    _add_rec(db, fid, 3, "down", "down", "low", "中性偏空", _tech(25, 0.008, -0.05))   # bear 命中
    _add_rec(db, fid, 4, "up", "down", "medium", "中性偏空", _tech(20, 0.005, -0.02))  # bear 错误
    _add_rec(db, fid, 5, "range", "range", "medium", "中性", _tech(50, 0.015, -0.10))  # sideways 命中
    db.commit()

    result = error_analysis(db, fund_id=fid)
    assert result["sample_count"] == 5
    envs = _envs(result)

    mkt = envs["market_regime"]
    assert mkt["bull"]["count"] == 2 and mkt["bull"]["hit_rate"] == 50.0 and mkt["bull"]["error_rate"] == 50.0
    assert mkt["bear"]["count"] == 2 and mkt["bear"]["hit_rate"] == 50.0
    assert mkt["sideways"]["count"] == 1 and mkt["sideways"]["hit_rate"] == 100.0
    assert mkt["sideways"]["error_rate"] == 0.0

    conf = envs["confidence"]
    assert conf["high"]["count"] == 2 and conf["high"]["hit_rate"] == 50.0
    assert conf["low"]["count"] == 1 and conf["low"]["hit_rate"] == 100.0
    assert conf["medium"]["count"] == 2 and conf["medium"]["hit_rate"] == 50.0

    rsi = envs["technical_rsi"]
    assert rsi["rsi>70"]["count"] == 2 and rsi["rsi>70"]["hit_rate"] == 50.0
    assert rsi["rsi<30"]["count"] == 2 and rsi["rsi<30"]["hit_rate"] == 50.0
    assert rsi["rsi_normal"]["count"] == 1 and rsi["rsi_normal"]["hit_rate"] == 100.0

    vol = envs["technical_volatility"]
    assert vol["high_volatility"]["count"] == 2 and vol["high_volatility"]["hit_rate"] == 50.0
    assert vol["low_volatility"]["count"] == 2 and vol["low_volatility"]["hit_rate"] == 50.0
    assert vol["normal_volatility"]["count"] == 1 and vol["normal_volatility"]["hit_rate"] == 100.0

    dd = envs["technical_drawdown"]
    assert dd["large_drawdown"]["count"] == 2 and dd["large_drawdown"]["hit_rate"] == 50.0
    assert dd["normal_drawdown"]["count"] == 3 and dd["normal_drawdown"]["hit_rate"] == round(2 / 3 * 100, 2)

    ft = envs["fund_type"]
    assert ft["混合型-偏股"]["count"] == 5 and ft["混合型-偏股"]["hit_rate"] == 60.0


def test_error_analysis_multi_environment(db):
    """多环境：不同基金类型/市场状态各自分组统计。"""
    f2 = _add_fund(db, "ERRANA02", "错误分析债券基金", fund_type="债券型")
    f3 = _add_fund(db, "ERRANA03", "错误分析科技基金", fund_type="股票型")
    db.flush()
    _add_rec(db, f2.id, 1, "up", "up", "high", "中性偏多", _tech(65, 0.012, -0.08))
    _add_rec(db, f2.id, 2, "down", "down", "low", "中性偏空", _tech(40, 0.009, -0.03))
    _add_rec(db, f3.id, 1, "up", "down", "high", "中性偏多", _tech(72, 0.035, -0.30))
    db.commit()

    # 债券型基金：两类环境全部命中
    envs2 = _envs(error_analysis(db, fund_id=f2.id))
    assert envs2["fund_type"]["债券型"]["count"] == 2
    assert envs2["fund_type"]["债券型"]["hit_rate"] == 100.0
    assert envs2["market_regime"]["bull"]["count"] == 1 and envs2["market_regime"]["bull"]["hit_rate"] == 100.0
    assert envs2["market_regime"]["bear"]["count"] == 1 and envs2["market_regime"]["bear"]["hit_rate"] == 100.0

    # 股票型基金：bull 环境预测错误
    envs3 = _envs(error_analysis(db, fund_id=f3.id))
    assert envs3["fund_type"]["股票型"]["count"] == 1
    assert envs3["fund_type"]["股票型"]["hit_rate"] == 0.0
    assert envs3["fund_type"]["股票型"]["error_rate"] == 100.0
    assert envs3["market_regime"]["bull"]["count"] == 1 and envs3["market_regime"]["bull"]["hit_rate"] == 0.0

    # 全量视角：包含多基金记录
    assert error_analysis(db)["sample_count"] >= 3


def test_error_analysis_boundaries(db):
    """边界情况：阈值边界、缺失快照、未知市场状态、缺失置信度不崩溃。"""
    fund = _add_fund(db, "ERRANA04", "错误分析边界基金")
    db.flush()
    fid = fund.id
    # rsi=70 → normal（>70 才超买）；vol=0.02 → high；mdd=-0.15 → large（<=-0.15）
    _add_rec(db, fid, 1, "up", "up", None, None, _tech(70, 0.02, -0.15))
    # 快照全缺失
    _add_rec(db, fid, 2, "up", "down", "high", None, None)
    # rsi=30 → normal；vol=0.01 → low；mdd=-0.149 → normal
    _add_rec(db, fid, 3, "down", "down", "medium", "中性", _tech(30, 0.01, -0.149))
    db.commit()

    result = error_analysis(db, fund_id=fid)
    assert result["sample_count"] == 3
    envs = _envs(result)

    rsi = envs["technical_rsi"]
    assert "rsi>70" not in rsi and "rsi<30" not in rsi
    assert rsi["rsi_normal"]["count"] == 2
    assert rsi["missing"]["count"] == 1

    vol = envs["technical_volatility"]
    assert vol["high_volatility"]["count"] == 1
    assert vol["low_volatility"]["count"] == 1
    assert vol["missing"]["count"] == 1

    dd = envs["technical_drawdown"]
    assert dd["large_drawdown"]["count"] == 1
    assert dd["normal_drawdown"]["count"] == 1
    assert dd["missing"]["count"] == 1

    mkt = envs["market_regime"]
    assert mkt["unknown"]["count"] == 2  # snapshot=None 与未知 label 都归 unknown
    assert mkt["sideways"]["count"] == 1

    conf = envs["confidence"]
    assert conf["unknown"]["count"] == 1
    assert conf["high"]["count"] == 1 and conf["medium"]["count"] == 1

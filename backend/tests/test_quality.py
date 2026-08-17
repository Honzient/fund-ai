"""预测质量分析测试（v0.3）：置信度/类别与未来收益的关系统计 + API。"""
from datetime import date, datetime, timezone

from app.models import Fund
from app.prediction.ledger import PredictionRecord, prediction_quality

_CONF = timezone.utc


def _add_fund(db, code: str, name: str) -> Fund:
    fund = Fund(
        fund_code=code, fund_name=name, fund_type="混合型",
        establish_date=date(2019, 1, 1), source="test",
    )
    db.add(fund)
    db.flush()
    return fund


def _add_rec(db, fund_id: int, day: int, horizon: str, cls, conf, ret, actual, days: int = 5):
    db.add(
        PredictionRecord(
            fund_id=fund_id,
            prediction_date=date(2024, 1, day),
            horizon=horizon,
            horizon_days=days,
            model_name="test-model",
            model_version="v0.3.0",
            calibrated=True,
            calibration_method="isotonic",
            predicted_class=cls,
            confidence_score=conf,
            actual_return=ret,
            actual_class=actual,
            evaluated_at=datetime(2024, 3, 1, tzinfo=_CONF),
        )
    )


def test_quality_empty(db):
    """空台账：sample_count=0，分组为空列表。"""
    fund = _add_fund(db, "QUALITY00", "质量空基金")
    db.commit()
    result = prediction_quality(db, fund_id=fund.id)
    assert result["sample_count"] == 0
    assert result["by_confidence"] == []
    assert result["by_class"] == []


def test_quality_normal_samples(db):
    """正常样本：按置信度区间/预测类别的收益与命中率统计（手算期望值）。"""
    fund = _add_fund(db, "QUALITY01", "质量样本基金")
    db.flush()
    fid = fund.id
    _add_rec(db, fid, 1, "short", "up", 0.85, 3.5, "up")        # 80%+ 命中
    _add_rec(db, fid, 2, "short", "up", 0.85, 1.0, "range")      # 80%+ 未中
    _add_rec(db, fid, 3, "short", "down", 0.70, -2.4, "down")    # 60-80% 命中
    _add_rec(db, fid, 4, "short", "range", 0.55, 0.2, "range")   # 50-60% 命中
    _add_rec(db, fid, 5, "medium", "up", 0.90, -0.5, "down")     # 80%+ 高置信未中
    _add_rec(db, fid, 6, "short", "up", None, 1.8, "up")         # 无置信度 命中
    db.commit()

    result = prediction_quality(db, fund_id=fid)
    assert result["sample_count"] == 6

    conf = {b["bucket"]: b for b in result["by_confidence"]}
    # 80%+：记录 1/2/5，收益 [3.5, 1.0, -0.5]，命中 1/3
    b = conf["80%+"]
    assert b["count"] == 3
    assert b["avg_forward_return"] == round((3.5 + 1.0 - 0.5) / 3, 4)
    assert b["median_forward_return"] == 1.0
    assert b["hit_rate"] == round(1 / 3 * 100, 2)
    # 60-80%：记录 3
    assert conf["60–80%"]["count"] == 1
    assert conf["60–80%"]["avg_forward_return"] == -2.4
    assert conf["60–80%"]["hit_rate"] == 100.0
    # 50-60%：记录 4
    assert conf["50–60%"]["count"] == 1
    assert conf["50–60%"]["avg_forward_return"] == 0.2
    # 无置信度：记录 6
    assert conf["无置信度"]["count"] == 1
    assert conf["无置信度"]["avg_forward_return"] == 1.8
    assert conf["无置信度"]["hit_rate"] == 100.0
    # 空区间不出现
    assert "<50%" not in conf

    cls = {b["bucket"]: b for b in result["by_class"]}
    # up：记录 1/2/5/6，收益 [3.5, 1.0, -0.5, 1.8]，命中 2/4
    b = cls["up"]
    assert b["count"] == 4
    assert b["avg_forward_return"] == round((3.5 + 1.0 - 0.5 + 1.8) / 4, 4)
    assert b["median_forward_return"] == 1.4
    assert b["hit_rate"] == 50.0
    assert b["directional_hit_rate"] == 50.0
    # down：记录 3，方向命中 100%
    assert cls["down"]["count"] == 1
    assert cls["down"]["avg_forward_return"] == -2.4
    assert cls["down"]["directional_hit_rate"] == 100.0
    # range：记录 4
    assert cls["range"]["count"] == 1
    assert cls["range"]["hit_rate"] == 100.0


def test_quality_multi_fund(db):
    """多基金：总体统计包含全部基金，fund_id 过滤后只含指定基金。"""
    f2 = _add_fund(db, "QUALITY02", "质量多基金A")
    f3 = _add_fund(db, "QUALITY03", "质量多基金B")
    db.flush()
    _add_rec(db, f2.id, 1, "short", "up", 0.82, 2.0, "up")
    _add_rec(db, f2.id, 2, "short", "down", 0.61, -1.0, "down")
    _add_rec(db, f3.id, 1, "short", "range", 0.52, 0.5, "range")
    db.commit()

    all_result = prediction_quality(db)
    assert all_result["sample_count"] >= 3
    assert prediction_quality(db, fund_id=f2.id)["sample_count"] == 2
    assert prediction_quality(db, fund_id=f3.id)["sample_count"] == 1
    assert all_result["by_class"][0]["count"] >= 1


def test_quality_by_horizon(db):
    """不同 horizon：按周期过滤统计。"""
    f4 = _add_fund(db, "QUALITY04", "质量周期基金")
    db.flush()
    _add_rec(db, f4.id, 1, "short", "up", 0.81, 1.5, "up", days=5)
    _add_rec(db, f4.id, 2, "short", "down", 0.62, -0.8, "down", days=5)
    _add_rec(db, f4.id, 3, "long", "up", 0.88, 6.0, "up", days=60)
    db.commit()

    assert prediction_quality(db, fund_id=f4.id)["sample_count"] == 3
    short = prediction_quality(db, fund_id=f4.id, horizon="short")
    assert short["sample_count"] == 2
    assert short["horizon"] == "short"
    long_q = prediction_quality(db, fund_id=f4.id, horizon="long")
    assert long_q["sample_count"] == 1
    assert long_q["by_class"][0]["avg_forward_return"] == 6.0
    assert prediction_quality(db, fund_id=f4.id, horizon="medium")["sample_count"] == 0


def test_quality_api(client, auth_headers, db):
    """API：GET /api/prediction/quality 返回 by_confidence/by_class/sample_count。"""
    fund = _add_fund(db, "QUALITY05", "质量API基金")
    db.flush()
    _add_rec(db, fund.id, 1, "short", "up", 0.86, 2.5, "up")
    db.commit()

    r = client.get("/api/prediction/quality", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"sample_count", "horizon", "by_confidence", "by_class"}
    assert isinstance(body["by_confidence"], list)
    assert isinstance(body["by_class"], list)

    r2 = client.get(f"/api/prediction/quality?fund_code={fund.fund_code}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["sample_count"] == 1
    assert r2.json()["by_confidence"][0]["avg_forward_return"] == 2.5

    r3 = client.get("/api/prediction/quality?horizon=bad", headers=auth_headers)
    assert r3.status_code == 422

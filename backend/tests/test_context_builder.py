"""ContextBuilder 测试：自动注入上下文结构完整性 + 多基金 data_as_of + context_hash。"""
import pytest

from app.llm import ContextBuilder, build_sources
from app.services import analysis_service


@pytest.fixture(autouse=True)
def patch_predict(monkeypatch):
    """避免测试中真实训练模型。"""

    def fake_predict(self, fund_code, horizon):
        return {
            "fund_code": fund_code,
            "model_version": "v1.0-test",
            "model_name": "logistic",
            "champion": True,
            "calibration_method": "isotonic",
            "calibrated": True,
            "horizon": horizon,
            "horizon_days": {"short": 5, "medium": 20, "long": 60}[horizon],
            "generated_at": "2026-01-01T00:00:00",
            "data_as_of": "2026-01-01",
            "raw_probabilities": {"up": 50.0, "range": 30.0, "down": 20.0},
            "calibrated_probabilities": {"up": 50.0, "range": 30.0, "down": 20.0},
            "probabilities": {"up": 50.0, "range": 30.0, "down": 20.0},
            "predicted_class": "up",
            "direction": "偏多",
            "confidence": "low",
            "confidence_score": 0.4,
            "feature_importance": [{"feature": "momentum_20d", "importance": 0.3}],
            "feature_snapshot": None,
            "market_snapshot": None,
            "disclaimer": "测试",
        }

    monkeypatch.setattr(analysis_service.PredictionEngine, "predict", fake_predict)


def test_build_context_structure():
    context = ContextBuilder().build(["110022", "005827"], "3M")
    assert context["generated_at"]
    assert context["latest_data_as_of"]
    assert context["context_hash"]
    assert len(context["context_hash"]) == 16
    assert context["context_version"] >= 2
    assert len(context["funds"]) == 2
    for fund in context["funds"]:
        assert fund["fund_profile"]["fund_code"] in ("110022", "005827")
        assert fund["fund_profile"]["fund_name"]
        assert fund["technical_indicators"].get("rsi14") is not None
        assert fund["risk_metrics"].get("sharpe") is not None
        probs = fund["prediction"]["short"]["probabilities"]
        assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100, abs=0.5)
        assert isinstance(fund["positive_factors"], list)
        assert isinstance(fund["main_risks"], list)
        assert fund["holdings"]["top10"] or fund["holdings"]["industry_distribution"]
        # 每只基金独立 data_as_of
        assert fund["data_as_of"]
    assert context["market"]["market_regime"]["label"] in ("偏多", "中性", "中性偏多", "中性偏空", "偏空")
    assert context["macro"]
    assert context["news"]
    assert context["policies"]


def test_build_context_unknown_fund():
    context = ContextBuilder().build(["999999"], "3M")
    assert context["funds"][0].get("error")


def test_multi_fund_data_as_of_independent():
    """多基金 Context：全局 latest_data_as_of 不被最后一只基金覆盖。"""
    context = ContextBuilder().build(["110022", "005827"], "3M")
    per_fund = [f["data_as_of"] for f in context["funds"] if "error" not in f]
    assert context["latest_data_as_of"] == max(per_fund)
    # latest_data_as_of 语义：全局最新；每只基金各自保留
    assert all(f.get("data_as_of") for f in context["funds"] if "error" not in f)


def test_context_hash_stable_for_same_input():
    """同一输入 → 相同 context_hash（规范化指纹）。"""
    c1 = ContextBuilder().build(["110022"], "3M")
    c2 = ContextBuilder().build(["110022"], "3M")
    assert c1["context_hash"] == c2["context_hash"]


def test_build_sources():
    context = ContextBuilder().build(["110022"], "3M")
    sources = build_sources(context)
    assert sources["funds"][0]["fund_code"] == "110022"
    assert sources["market"] is True
    assert sources["macro"] > 0
    assert sources["news_count"] > 0
    assert sources["prediction"] is True
    assert sources["data_as_of"] == context["latest_data_as_of"]
    assert sources["context_hash"] == context["context_hash"]

"""API 集成测试：认证 / 数据权限 / 自选 / 分析 / 对话 / 调度 / 设置。"""
import pytest

from app.services import analysis_service


@pytest.fixture(autouse=True)
def patch_predict(monkeypatch):
    """避免测试中真实训练模型（集成测试只验证链路）。"""

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
            "raw_probabilities": {"up": 55.0, "range": 30.0, "down": 15.0},
            "calibrated_probabilities": {"up": 55.0, "range": 30.0, "down": 15.0},
            "probabilities": {"up": 55.0, "range": 30.0, "down": 15.0},
            "predicted_class": "up",
            "direction": "偏多",
            "confidence": "medium",
            "confidence_score": 0.5,
            "feature_importance": [],
            "feature_snapshot": None,
            "market_snapshot": None,
            "disclaimer": "历史回测不代表未来表现。",
        }

    monkeypatch.setattr(analysis_service.PredictionEngine, "predict", fake_predict)


def test_unauthorized(client):
    assert client.get("/api/funds").status_code == 401
    assert client.get("/api/watchlist").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401


def test_login_and_me(client, auth_headers):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "wrong"})
    assert r.status_code == 401
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["username"] == "demo"


def test_register_and_isolation(client):
    r = client.post("/api/auth/register", json={"username": "alice", "password": "alice123"})
    assert r.status_code == 200
    alice = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # 新用户自选为空
    assert client.get("/api/watchlist", headers=alice).json() == []
    # 新用户无法修改 demo 用户的自选（数据权限）
    demo_wl = client.get("/api/watchlist", headers={
        "Authorization": f"Bearer {client.post('/api/auth/login', json={'username': 'demo', 'password': 'demo123456'}).json()['access_token']}"
    }).json()
    if demo_wl:
        assert client.delete(f"/api/watchlist/{demo_wl[0]['id']}", headers=alice).status_code == 404


def test_watchlist_crud(client, auth_headers):
    r = client.post("/api/watchlist", json={"fund_code": "260108", "group_name": "核心基金"}, headers=auth_headers)
    assert r.status_code == 200
    item = r.json()
    assert item["group_name"] == "核心基金"
    # 重复添加报错
    assert client.post("/api/watchlist", json={"fund_code": "260108"}, headers=auth_headers).status_code == 400
    # 分组与置顶
    r = client.patch(f"/api/watchlist/{item['id']}", json={"pinned": True, "group_name": "科技"}, headers=auth_headers)
    assert r.json()["pinned"] is True
    assert r.json()["group_name"] == "科技"
    groups = client.get("/api/watchlist/groups", headers=auth_headers).json()
    assert "科技" in groups
    assert client.delete(f"/api/watchlist/{item['id']}", headers=auth_headers).status_code == 200


def test_funds_endpoints(client, auth_headers):
    r = client.get("/api/funds?search=110022", headers=auth_headers)
    assert r.status_code == 200 and r.json()[0]["fund_code"] == "110022"
    r = client.get("/api/funds/110022", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["fund_name"]
    assert data["ai_score"] is not None
    assert data["trend"]["short"] in ("偏多", "中性", "偏空")
    r = client.get("/api/funds/110022/history", headers=auth_headers)
    assert r.json()["count"] > 500
    r = client.get("/api/funds/110022/indicators", headers=auth_headers)
    assert r.json()["indicators"]["ma20"]
    r = client.get("/api/funds/110022/risk", headers=auth_headers)
    assert "sharpe" in r.json()["metrics"]
    r = client.get("/api/funds/110022/analysis", headers=auth_headers)
    assert 0 <= r.json()["score"] <= 100
    r = client.get("/api/funds/110022/prediction?horizon=short", headers=auth_headers)
    probs = r.json()["probabilities"]
    assert probs["up"] + probs["range"] + probs["down"] == pytest.approx(100, abs=0.5)
    r = client.get("/api/funds/999999", headers=auth_headers)
    assert r.status_code == 404


def test_market_and_data(client, auth_headers):
    r = client.get("/api/market/overview", headers=auth_headers)
    assert r.json()["market_regime"]["label"]
    r = client.get("/api/market/indexes", headers=auth_headers)
    assert len(r.json()) >= 8
    r = client.get("/api/market/indexes/000300/history", headers=auth_headers)
    assert r.json()["count"] > 300
    r = client.get("/api/news", headers=auth_headers)
    assert r.json()["items"]
    r = client.get("/api/policies", headers=auth_headers)
    assert r.json()["items"]
    r = client.get("/api/macro", headers=auth_headers)
    assert r.json()["indicators"]


def test_chat_flow(client, auth_headers):
    r = client.post(
        "/api/chat",
        json={"message": "现在适合买入吗？", "fund_ids": ["110022"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fallback"] is True  # 无 API Key → 量化引擎降级摘要
    assert "110022" in data["reply"]
    conv_id = data["conversation_id"]
    # 历史与来源
    r = client.get(f"/api/chat/conversations/{conv_id}", headers=auth_headers)
    messages = r.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    r = client.get(f"/api/chat/conversations/{conv_id}/sources", headers=auth_headers)
    assert r.json()["available"] is True
    r = client.get("/api/chat/conversations", headers=auth_headers)
    assert any(c["id"] == conv_id for c in r.json())
    assert client.delete(f"/api/chat/conversations/{conv_id}", headers=auth_headers).status_code == 200


def test_analysis_compare(client, auth_headers):
    r = client.post(
        "/api/analysis",
        json={"fund_ids": ["110022", "000032"], "time_range": "3M"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    comparison = r.json()["comparison"]
    assert len(comparison["table"]) == 2
    assert comparison["highest_score"]


def test_schedules_crud(client, auth_headers):
    r = client.post(
        "/api/schedules",
        json={
            "name": "收盘分析", "schedule_type": "daily", "time_of_day": "16:00",
            "fund_ids": ["110022"], "enabled": False,
            "notification_channels": ["in_app"], "llm_summary": False,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    sched = r.json()
    r = client.patch(f"/api/schedules/{sched['id']}", json={"enabled": True, "time_of_day": "15:10"}, headers=auth_headers)
    assert r.json()["next_run_at"]
    assert client.get("/api/schedules", headers=auth_headers).json()
    assert client.delete(f"/api/schedules/{sched['id']}", headers=auth_headers).status_code == 200


def test_reports_and_notifications(client, auth_headers):
    import time

    r = client.post("/api/reports/generate", headers=auth_headers)
    assert r.status_code == 200
    # 报告生成为后台任务：轮询等待完成（最多 20s）
    reports = []
    for _ in range(20):
        time.sleep(1)
        r = client.get("/api/reports", headers=auth_headers)
        reports = r.json()
        if reports:
            break
    assert reports, "后台报告任务 20s 内未完成"
    r = client.get(f"/api/reports/{reports[0]['id']}", headers=auth_headers)
    body = r.json()
    assert body["content_md"] and body["content_html"]
    assert "市场概况" in body["content_md"]
    r = client.get("/api/notifications", headers=auth_headers)
    assert r.json()


def test_settings_and_key_encryption(client, auth_headers, db):
    r = client.get("/api/settings", headers=auth_headers)
    assert r.json()["llm"]["provider"] == "deepseek"
    r = client.post("/api/settings/keys", json={"deepseek_api_key": "sk-test-abcdef123456"}, headers=auth_headers)
    assert r.status_code == 200
    # 密钥加密存储：数据库中不可见明文
    from app.models import UserSetting

    row = db.query(UserSetting).filter(UserSetting.key == "deepseek_api_key").first()
    assert row.secret and row.secret != "sk-test-abcdef123456"
    from app.core.security import decrypt_secret

    assert decrypt_secret(row.secret) == "sk-test-abcdef123456"
    r = client.get("/api/settings", headers=auth_headers)
    assert r.json()["llm"]["has_user_key"] is True
    assert client.delete("/api/settings/keys/deepseek", headers=auth_headers).status_code == 200


def test_daily_summary(client, auth_headers):
    r = client.get("/api/summary/daily", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["market"]["label"]
    assert data["watchlist"].get("best") or data["text"]


def test_prediction_ledger_endpoint(client, auth_headers):
    """预测台账：分析接口已产生预测 → 台账可查询（含统计）。"""
    r = client.get("/api/funds/110022/prediction?horizon=short", headers=auth_headers)
    assert r.status_code == 200
    pred = r.json()
    assert pred["raw_probabilities"]
    assert pred["calibrated_probabilities"]
    assert pred["calibration_method"] in ("isotonic", "sigmoid", "uncalibrated")
    r = client.get("/api/prediction/ledger?fund_code=110022", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "records" in data and "stats" in data
    assert len(data["records"]) >= 1
    record = data["records"][0]
    assert record["raw_probabilities"] or record["calibrated_probabilities"]


def test_model_health_endpoint(client, auth_headers):
    r = client.get("/api/prediction/health", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "short" in data
    entry = data["short"]
    assert entry["status"] in ("no_model", "healthy", "warning", "degraded", "insufficient_data")
    assert entry["note"]


def test_backtest_has_baselines(client, auth_headers):
    import time

    # 后台先训练一个模型（若无），保证回测可用；测试用 mock 数据由 /retrain 触发
    r = client.post("/api/prediction/retrain?horizon=short", headers=auth_headers)
    assert r.status_code == 200
    for _ in range(30):
        time.sleep(2)
        r = client.get("/api/prediction/models", headers=auth_headers)
        if r.json():
            break
    r = client.get("/api/prediction/backtest/latest?horizon=short", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    if data.get("available"):
        assert "momentum" in data["baselines"]
        assert data["metrics"].get("brier_score") is not None or data["metrics"].get("accuracy") is not None


def test_tasks(client, auth_headers):
    r = client.get("/api/tasks", headers=auth_headers)
    assert isinstance(r.json(), list)

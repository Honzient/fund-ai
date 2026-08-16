"""pytest 配置：隔离的临时 SQLite + mock 数据源 + 演示数据。"""
import os
import tempfile
from pathlib import Path

# 必须在导入 app 前设置环境变量
# 注意：沙箱环境下 tempfile.mkdtemp 创建的目录不允许再建子目录，改用 Path.mkdir；
# 每次会话开始前清空测试根目录，保证测试可重复运行。
import shutil  # noqa: E402

_TEST_ROOT_PATH = Path(tempfile.gettempdir()) / "fund_test_root"
if _TEST_ROOT_PATH.exists():
    shutil.rmtree(_TEST_ROOT_PATH, ignore_errors=True)
_TEST_ROOT_PATH.mkdir(parents=True, exist_ok=True)
_TEST_ROOT = str(_TEST_ROOT_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_ROOT}/test.db"
os.environ["DATA_PROVIDER_ORDER"] = "mock"
os.environ["ENABLE_AUTO_SYNC"] = "false"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["STORAGE_DIR"] = os.path.join(_TEST_ROOT, "storage")
os.environ["LOG_DIR"] = os.path.join(_TEST_ROOT, "logs")
os.environ["CACHE_TTL_SECONDS"] = "60"
os.environ["MODEL_JOBS"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.data.seeds import seed_demo_data  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def client(_setup_db):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

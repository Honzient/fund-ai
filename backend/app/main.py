"""FastAPI 应用入口。"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import SessionLocal, init_db
from app.scheduler import get_scheduler

log = get_logger("app")


def _find_frontend_dist() -> Path | None:
    """前端构建产物位置：环境变量 > 开发目录 > PyInstaller 打包目录。"""
    candidates: list[Path] = []
    env = os.environ.get("FUNDAI_FRONTEND_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "frontend_dist")
    for candidate in candidates:
        if candidate.exists() and (candidate / "index.html").exists():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    log.info("启动 %s v%s", settings.APP_NAME, settings.APP_VERSION)
    init_db()
    from app.data.seeds import seed_demo_data

    db = SessionLocal()
    try:
        seed_result = seed_demo_data(db)
        log.info("数据初始化: %s", seed_result)
    finally:
        db.close()
    scheduler = get_scheduler()
    scheduler.start()
    # 预测模型预热：后台训练缺失的 Champion（不阻塞启动，predict 期间用统计基线）
    try:
        from app.prediction.retraining import RetrainingManager
        from app.services import analysis_service

        RetrainingManager(analysis_service.get_engine()).warmup()
    except Exception:  # noqa: BLE001
        log.warning("模型预热启动失败（不影响主流程）", exc_info=True)
    yield
    scheduler.shutdown()
    log.info("应用已停止")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "基金智能分析预测平台 API。所有预测输出均为概率、评分、置信度与情景分析，"
            "不构成投资建议，不承诺收益。"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    # 若前端已构建，直接由后端托管静态文件
    frontend_dist = _find_frontend_dist()
    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    return app


app = create_app()

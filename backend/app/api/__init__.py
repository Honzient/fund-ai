"""API 路由聚合。"""
from fastapi import APIRouter

from app.api import auth, chat, data_api, funds, market, schedules, watchlist
from app.api.analysis import router as analysis_router
from app.api.misc import (
    health_router,
    notification_router,
    report_router,
    settings_router,
    summary_router,
    task_router,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth.router)
api_router.include_router(funds.router)
api_router.include_router(watchlist.router)
api_router.include_router(market.router)
api_router.include_router(data_api.macro_router)
api_router.include_router(data_api.news_router)
api_router.include_router(data_api.policy_router)
api_router.include_router(analysis_router)
api_router.include_router(chat.router)
api_router.include_router(schedules.router)
api_router.include_router(report_router)
api_router.include_router(notification_router)
api_router.include_router(task_router)
api_router.include_router(settings_router)
api_router.include_router(summary_router)

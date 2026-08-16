"""宏观 / 新闻 / 政策接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import MacroData, News, Policy, User
from app.services import news_service, sync_service
from app.tasks import get_task_manager

macro_router = APIRouter(prefix="/macro", tags=["macro"])


@macro_router.get("")
def list_macro(
    indicator: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    indicators = [r[0] for r in db.query(MacroData.indicator).distinct().order_by(MacroData.indicator).all()]
    q = db.query(MacroData)
    if indicator:
        q = q.filter(MacroData.indicator == indicator)
    rows = q.order_by(MacroData.period.desc()).limit(300).all()
    return {
        "items": [
            {
                "id": r.id,
                "indicator": r.indicator,
                "value": r.value,
                "unit": r.unit,
                "period": r.period,
                "change": r.change,
                "source": r.source,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in rows
        ],
        "indicators": indicators,
    }


news_router = APIRouter(prefix="/news", tags=["news"])


@news_router.get("")
def list_news(
    limit: int = Query(default=50, ge=1, le=200),
    industry: str | None = None,
    related_fund: str | None = None,
    min_importance: float | None = Query(default=None, ge=0, le=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items = news_service.news_list(db, limit, industry, related_fund, min_importance)
    if not items:
        news_service.sync_news(db)
        items = news_service.news_list(db, limit, industry, related_fund, min_importance)
    return {"items": items}


@news_router.get("/{news_id}")
def get_news(news_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    row = db.get(News, news_id)
    if row is None:
        raise HTTPException(status_code=404, detail="新闻不存在")
    return news_service._news_dict(row)


@news_router.post("/sync")
def sync_news(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    result = get_task_manager().run("sync.news", lambda: sync_service.sync_news_policies(), retries=1)
    return {"task_id": result["task_id"], "status": "started"}


policy_router = APIRouter(prefix="/policies", tags=["policies"])


@policy_router.get("")
def list_policies(
    limit: int = Query(default=50, ge=1, le=200),
    industry: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items = news_service.policy_list(db, limit, industry)
    if not items:
        news_service.sync_policies(db)
        items = news_service.policy_list(db, limit, industry)
    return {"items": items}


@policy_router.get("/{policy_id}")
def get_policy(policy_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    row = db.get(Policy, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="政策不存在")
    return news_service._policy_dict(row)


@policy_router.post("/sync")
def sync_policies(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    result = get_task_manager().run("sync.policies", lambda: sync_service.sync_news_policies(), retries=1)
    return {"task_id": result["task_id"], "status": "started"}

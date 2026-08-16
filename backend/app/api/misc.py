"""报告 / 通知 / 任务 / 设置 / 总结 / 健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.llm import get_llm_manager
from app.models import Notification, Report, User
from app.schemas.settings import KeySetRequest, SettingsUpdate
from app.services import report_service, settings_service, summary_service
from app.tasks import get_task_manager

report_router = APIRouter(prefix="/reports", tags=["reports"])


@report_router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Report)
        .filter(Report.user_id == user.id)
        .order_by(Report.generated_at.desc())
        .limit(100)
        .all()
    )
    return [report_service.report_to_dict(r, include_content=False) for r in rows]


@report_router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Report).filter(Report.id == report_id, Report.user_id == user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report_service.report_to_dict(row)


@report_router.post("/generate")
def generate_report(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.tasks import generate_report_for_user

    result = get_task_manager().run(
        f"report.generate.user{user.id}",
        lambda: generate_report_for_user(user.id),
        retries=0,
    )
    return {"task_id": result["task_id"], "status": "started"}


notification_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notification_router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "content": r.content,
            "type": r.type,
            "read": r.read,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@notification_router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="通知不存在")
    row.read = True
    db.commit()
    return {"status": "read"}


@notification_router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.read.is_(False)
    ).update({"read": True})
    db.commit()
    return {"status": "read"}


task_router = APIRouter(prefix="/tasks", tags=["tasks"])


@task_router.get("")
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(get_current_user),
):
    return get_task_manager().recent(limit)


settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("")
def get_settings_api(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return settings_service.get_settings_payload(db, user.id)


@settings_router.put("")
def update_settings_api(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return settings_service.update_settings(db, user.id, payload.model_dump(exclude_none=True))


@settings_router.post("/keys")
def set_api_key(
    payload: KeySetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """用户自定义 DeepSeek API Key（后端加密存储，永不回显）。"""
    return settings_service.set_api_key(db, user.id, payload.deepseek_api_key)


@settings_router.delete("/keys/deepseek")
def delete_api_key(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return settings_service.delete_api_key(db, user.id)


summary_router = APIRouter(tags=["summary"])


@summary_router.get("/summary/daily")
def daily_summary(user: User = Depends(get_current_user)):
    return summary_service.daily_summary(user.id)


health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "db": "ok",
        "llm": "configured" if get_llm_manager().available() else "missing",
        "data_provider": ",".join(settings.provider_order),
        "time": __import__("datetime").datetime.now().isoformat(),
    }

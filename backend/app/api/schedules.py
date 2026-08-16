"""定时分析任务接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ScheduledAnalysis, User
from app.scheduler import compute_next_run_time, get_scheduler
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _dict(row: ScheduledAnalysis) -> dict:
    next_run = compute_next_run_time(
        row.schedule_type, row.time_of_day, row.day_of_week, row.day_of_month, row.cron_expression
    ) if row.enabled else None
    return {
        "id": row.id,
        "name": row.name,
        "schedule_type": row.schedule_type,
        "cron_expression": row.cron_expression,
        "time_of_day": row.time_of_day,
        "day_of_week": row.day_of_week,
        "day_of_month": row.day_of_month,
        "fund_ids": row.fund_ids or [],
        "enabled": row.enabled,
        "notification_channels": row.notification_channels or ["in_app"],
        "llm_summary": row.llm_summary,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "next_run_at": next_run,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def list_schedules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(ScheduledAnalysis)
        .filter(ScheduledAnalysis.user_id == user.id)
        .order_by(ScheduledAnalysis.id)
        .all()
    )
    return [_dict(r) for r in rows]


@router.post("")
def create_schedule(
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = ScheduledAnalysis(
        user_id=user.id,
        name=payload.name,
        schedule_type=payload.schedule_type,
        cron_expression=payload.cron_expression,
        time_of_day=payload.time_of_day,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        fund_ids=payload.fund_ids,
        enabled=payload.enabled,
        notification_channels=payload.notification_channels,
        llm_summary=payload.llm_summary,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.enabled:
        get_scheduler().add_user_schedule(row)
    return _dict(row)


@router.patch("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(ScheduledAnalysis)
        .filter(ScheduledAnalysis.id == schedule_id, ScheduledAnalysis.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    for field in (
        "name", "schedule_type", "time_of_day", "day_of_week", "day_of_month",
        "cron_expression", "fund_ids", "enabled", "notification_channels", "llm_summary",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    scheduler = get_scheduler()
    scheduler.remove_user_schedule(row.id)
    if row.enabled:
        scheduler.add_user_schedule(row)
    return _dict(row)


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(ScheduledAnalysis)
        .filter(ScheduledAnalysis.id == schedule_id, ScheduledAnalysis.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    get_scheduler().remove_user_schedule(row.id)
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


@router.post("/{schedule_id}/run")
def run_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(ScheduledAnalysis)
        .filter(ScheduledAnalysis.id == schedule_id, ScheduledAnalysis.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return get_scheduler().run_now(row.id)

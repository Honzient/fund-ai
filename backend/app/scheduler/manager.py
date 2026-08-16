"""调度器：数据同步 + 用户定时分析任务（APScheduler）。

- 行情估值刷新：每 QUOTE_SYNC_MINUTES 分钟
- 每日数据同步：DAILY_SYNC_TIME
- 用户定时分析：按 schedule_type / cron 表达式
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import ScheduledAnalysis
from app.tasks import get_task_manager, run_scheduled_analysis, sync_all_data, sync_quotes

log = get_logger("app.task")


def _cron_for(schedule: ScheduledAnalysis) -> str | None:
    if schedule.schedule_type == "cron":
        return schedule.cron_expression
    if not schedule.time_of_day:
        return None
    hour, minute = schedule.time_of_day.split(":")
    if schedule.schedule_type == "daily":
        return f"{int(minute)} {int(hour)} * * *"
    if schedule.schedule_type == "weekly":
        dow = schedule.day_of_week if schedule.day_of_week is not None else 0
        return f"{int(minute)} {int(hour)} * * {dow}"
    if schedule.schedule_type == "monthly":
        dom = schedule.day_of_month if schedule.day_of_month is not None else 1
        return f"{int(minute)} {int(hour)} {dom} * *"
    return None


def compute_next_run_time(schedule_type: str, time_of_day: str | None,
                          day_of_week: int | None, day_of_month: int | None,
                          cron_expression: str | None) -> str | None:
    """计算下一次运行时间（用于 API 展示）。"""
    from datetime import datetime, timedelta

    settings = get_settings()
    try:
        tz = ZoneInfo(settings.TZ)
    except Exception:  # noqa: BLE001
        tz = None
    now = datetime.now(tz)
    if schedule_type == "cron" and cron_expression:
        try:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=tz)
            nxt = trigger.get_next_fire_time(None, now)
            return nxt.isoformat() if nxt else None
        except Exception:  # noqa: BLE001
            return None
    if not time_of_day:
        return None
    hour, minute = (int(x) for x in time_of_day.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule_type == "daily":
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.isoformat()
    if schedule_type == "weekly":
        dow = day_of_week if day_of_week is not None else 0
        days_ahead = (dow - now.weekday()) % 7
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate.isoformat()
    if schedule_type == "monthly":
        dom = min(day_of_month if day_of_month is not None else 1, 28)
        candidate = now.replace(day=dom, hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            month = now.month + 1
            year = now.year + (1 if month > 12 else 0)
            if month > 12:
                month = 1
            candidate = now.replace(
                year=year, month=month, day=dom, hour=hour, minute=minute, second=0, microsecond=0
            )
        return candidate.isoformat()
    return None


class SchedulerManager:
    def __init__(self) -> None:
        settings = get_settings()
        try:
            tz = ZoneInfo(settings.TZ)
        except Exception:  # noqa: BLE001
            tz = None
        self.scheduler = AsyncIOScheduler(timezone=tz)
        self._settings = settings

    # ------------------------------------------------------------ 生命周期

    def start(self) -> None:
        self._add_system_jobs()
        self._reload_user_jobs()
        self.scheduler.start()
        log.info("调度器已启动")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        log.info("调度器已停止")

    def _add_system_jobs(self) -> None:
        if self._settings.ENABLE_AUTO_SYNC:
            interval = max(1, self._settings.QUOTE_SYNC_MINUTES)
            self.scheduler.add_job(
                self._task_wrapper("sync.quotes", sync_quotes),
                IntervalTrigger(minutes=interval),
                id="sync.quotes",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            hour, minute = (int(x) for x in self._settings.DAILY_SYNC_TIME.split(":"))
            self.scheduler.add_job(
                self._task_wrapper("sync.daily", sync_all_data),
                CronTrigger(hour=hour, minute=minute),
                id="sync.daily",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            log.info(
                "系统任务已注册: 行情刷新每 %d 分钟 / 数据同步每天 %s",
                interval, self._settings.DAILY_SYNC_TIME,
            )

    def _task_wrapper(self, name, fn):
        def _job():
            get_task_manager().run(name, fn, retries=1)

        return _job

    # ------------------------------------------------------------ 用户任务

    def _reload_user_jobs(self) -> None:
        db = SessionLocal()
        try:
            rows = db.query(ScheduledAnalysis).filter(ScheduledAnalysis.enabled.is_(True)).all()
            for row in rows:
                self.add_user_schedule(row)
        finally:
            db.close()

    def add_user_schedule(self, schedule: ScheduledAnalysis) -> None:
        job_id = f"analysis:{schedule.id}"
        cron = _cron_for(schedule)
        if not cron:
            log.warning("定时任务 %s 无法解析 cron，跳过", schedule.id)
            return
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=self.scheduler.timezone)
        except Exception as exc:  # noqa: BLE001
            log.warning("定时任务 %s cron 无效(%s): %s", schedule.id, cron, exc)
            return
        self.scheduler.add_job(
            self._task_wrapper(
                f"analysis:{schedule.id}",
                lambda: run_scheduled_analysis(schedule.id),
            ),
            trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        log.info("定时分析任务已注册: %s (%s)", schedule.name, cron)

    def remove_user_schedule(self, schedule_id: int) -> None:
        job_id = f"analysis:{schedule_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            log.info("定时分析任务已移除: %s", job_id)

    def run_now(self, schedule_id: int) -> dict:
        """手动触发定时分析任务（异步后台执行）。"""
        get_task_manager().run(f"analysis:{schedule_id}", lambda: run_scheduled_analysis(schedule_id), retries=0)
        return {"status": "started"}


_scheduler_manager: SchedulerManager | None = None


def get_scheduler() -> SchedulerManager:
    global _scheduler_manager
    if _scheduler_manager is None:
        _scheduler_manager = SchedulerManager()
    return _scheduler_manager

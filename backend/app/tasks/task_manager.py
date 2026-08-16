"""任务管理器：所有后台任务（数据同步/分析/报告/通知）统一记录状态、错误与重试。"""
from __future__ import annotations

from typing import Any, Callable

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import TaskRun
from app.utils.dates import utcnow

log = get_logger("app.task")


class TaskManager:
    def _create(self, name: str) -> TaskRun:
        db = SessionLocal()
        try:
            run = TaskRun(name=name, status="running", started_at=utcnow())
            db.add(run)
            db.commit()
            db.refresh(run)
            return run.id
        finally:
            db.close()

    def _update(self, run_id: int, **fields) -> None:
        db = SessionLocal()
        try:
            row = db.get(TaskRun, run_id)
            if row:
                for key, value in fields.items():
                    setattr(row, key, value)
                db.commit()
        finally:
            db.close()

    def run(self, name: str, fn: Callable[[], Any], retries: int = 1) -> dict:
        """执行任务并记录。fn 抛异常时重试，最终失败记录 error。"""
        run_id = self._create(name)
        attempt = 0
        while True:
            try:
                result = fn()
                self._update(
                    run_id, status="success", finished_at=utcnow(), retries=attempt, result=result
                )
                return {"task_id": run_id, "status": "success", "result": result}
            except Exception as exc:  # noqa: BLE001
                log.exception("任务 %s 失败(第 %d 次尝试): %s", name, attempt + 1, exc)
                attempt += 1
                if attempt > retries:
                    self._update(
                        run_id,
                        status="failed",
                        finished_at=utcnow(),
                        retries=attempt - 1,
                        error=str(exc)[:2000],
                    )
                    return {"task_id": run_id, "status": "failed", "error": str(exc)[:500]}

    def recent(self, limit: int = 50) -> list[dict]:
        db = SessionLocal()
        try:
            rows = db.query(TaskRun).order_by(TaskRun.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "error": r.error,
                    "retries": r.retries,
                    "result": r.result,
                }
                for r in rows
            ]
        finally:
            db.close()


_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

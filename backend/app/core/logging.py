"""统一日志系统。

- logs/app.log    应用日志
- logs/data.log   数据源日志
- logs/llm.log    LLM 日志
- logs/task.log   任务 / 调度日志
绝不记录 API Key / 密码 / 敏感信息。
"""
from __future__ import annotations

import logging
import logging.handlers

from app.core.config import get_settings
from app.core.security import redact


class RedactFilter(logging.Filter):
    """对日志内容做脱敏：API Key / 密码 / Bearer token。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            record.msg = redact(msg)
            record.args = ()
        except Exception:
            pass
        return True


_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    for filename, logger_name in (
        ("app.log", None),
        ("data.log", "app.data"),
        ("llm.log", "app.llm"),
        ("task.log", "app.task"),
    ):
        handler = logging.handlers.RotatingFileHandler(
            log_dir / filename, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(fmt)
        handler.addFilter(RedactFilter())
        if logger_name is None:
            root.addHandler(handler)
        else:
            lg = logging.getLogger(logger_name)
            lg.addHandler(handler)
            lg.setLevel(settings.LOG_LEVEL.upper())
    _configured = True
    # 第三方库日志降噪（httpx/httpcore 的请求日志、watchfiles 等）
    for noisy in ("httpx", "httpcore", "watchfiles", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)

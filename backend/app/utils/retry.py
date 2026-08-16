"""异步重试：指数退避 + 抖动，用于所有外部 API 调用。"""
from __future__ import annotations

import asyncio
import random
from functools import wraps

from app.core.logging import get_logger

log = get_logger("app.retry")

RETRIABLE = (TimeoutError, ConnectionError, OSError)


def async_retry(
    max_retries: int = 2,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    retriable: tuple = RETRIABLE,
):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except retriable as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt >= max_retries:
                        break
                    wait = delay + random.uniform(0, 0.5)
                    log.warning(
                        "%s 调用失败(第 %d 次): %s，%.2fs 后重试",
                        fn.__name__, attempt + 1, exc, wait,
                    )
                    await asyncio.sleep(wait)
                    delay *= backoff
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator

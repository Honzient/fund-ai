"""数据源限流：同源请求最小间隔控制，避免触发目标站点限流。"""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, min_interval: float = 0.35):
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

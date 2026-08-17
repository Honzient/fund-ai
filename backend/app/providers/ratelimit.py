"""数据源限流：同源请求最小间隔控制（线程安全时间锁，无事件循环绑定问题）。"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, min_interval: float = 0.35):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

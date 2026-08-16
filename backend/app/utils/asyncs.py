"""在同步上下文（FastAPI 线程池 / APScheduler executor）中运行协程。"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_async(coro: Coroutine) -> Any:
    """无运行中事件循环时 asyncio.run；已有循环时转入独立线程执行。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()

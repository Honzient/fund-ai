"""缓存层：本地 TTL 缓存（默认）/ Redis（可选）。

缓存对象：基金数据、市场数据、新闻、政策、LLM Context、LLM Response。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("app.cache")


class TTLCache:
    """线程安全的本地 TTL 缓存。"""

    def __init__(self, maxsize: int = 1024, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.RLock()
        self.maxsize = maxsize
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires = item
            if expires is not None and time.time() > expires:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if ttl is None:
            ttl = self.default_ttl
        with self._lock:
            if len(self._store) >= self.maxsize:
                now = time.time()
                for k in [k for k, (_, exp) in self._store.items() if exp is not None and exp < now]:
                    self._store.pop(k, None)
                if len(self._store) >= self.maxsize:
                    oldest = next(iter(self._store), None)
                    if oldest:
                        self._store.pop(oldest, None)
            self._store[key] = (value, time.time() + ttl if ttl > 0 else None)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


class RedisCache:
    """Redis 缓存（可选，REDIS_URL 配置后启用）。"""

    def __init__(self, url: str, default_ttl: int = 300):
        import redis  # 延迟导入

        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3)
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        try:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            self.client.setex(
                key,
                ttl if ttl is not None else self.default_ttl,
                json.dumps(value, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            log.warning("Redis 写入失败: %s", exc)

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            self.client.flushdb()
        except Exception:
            pass


class CacheManager:
    """单例缓存管理器，按配置选择后端。"""

    _instance: "CacheManager | None" = None

    def __init__(self):
        settings = get_settings()
        if settings.REDIS_URL:
            try:
                self.backend: Any = RedisCache(settings.REDIS_URL, settings.CACHE_TTL_SECONDS)
                self.backend_name = "redis"
                return
            except Exception as exc:
                log.warning("Redis 不可用，降级为本地缓存: %s", exc)
        self.backend = TTLCache(default_ttl=settings.CACHE_TTL_SECONDS)
        self.backend_name = "local"

    def get(self, key: str) -> Any | None:
        return self.backend.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.backend.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self.backend.delete(key)

    def clear(self) -> None:
        self.backend.clear()

    @classmethod
    def instance(cls) -> "CacheManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def get_cache() -> CacheManager:
    return CacheManager.instance()

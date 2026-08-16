"""Provider 注册表：按优先级调用多个数据源，失败自动 fallback，结果走缓存。"""
from __future__ import annotations

import json
from typing import Any

from app.cache.cache import CacheManager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import DataProvider

log = get_logger("app.data")


class ProviderRegistry:
    def __init__(self, providers: list[DataProvider], cache: CacheManager):
        self.providers = providers
        self.cache = cache
        self._settings = get_settings()

    @property
    def active_provider_names(self) -> list[str]:
        return [p.name for p in self.providers]

    def _cache_key(self, method: str, kwargs: dict) -> str:
        payload = json.dumps(kwargs, ensure_ascii=False, default=str, sort_keys=True)
        return f"provider:{method}:{payload}"

    async def call(
        self,
        method: str,
        default: Any = None,
        use_cache: bool = True,
        ttl: int | None = None,
        **kwargs,
    ) -> Any:
        """依次尝试每个 Provider，返回第一个非空结果。

        空结果（None / [] / {}）视为未命中，继续尝试下一个 Provider。
        全部失败返回 default。
        """
        cache_key = self._cache_key(method, kwargs)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        errors: list[str] = []
        for provider in self.providers:
            fn = getattr(provider, method, None)
            if fn is None:
                continue
            try:
                result = await fn(**kwargs)
                if result not in (None, [], {}):
                    if use_cache:
                        self.cache.set(cache_key, result, ttl)
                    return result
            except Exception as exc:  # noqa: BLE001 任何 Provider 异常都不能中断 fallback 链
                errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
                log.warning("Provider[%s].%s 失败: %s", provider.name, method, exc)
        if errors:
            log.warning("Provider 调用 %s 全部失败（%s），返回默认值", method, "; ".join(errors))
        return default

    async def call_first(
        self, method: str, default: Any = None, use_cache: bool = True, ttl: int | None = None, **kwargs
    ) -> Any:
        """只尝试第一个（优先级最高）Provider，用于明确要求真实数据源的场景。"""
        if not self.providers:
            return default
        provider = self.providers[0]
        fn = getattr(provider, method, None)
        if fn is None:
            return default
        cache_key = self._cache_key(method, kwargs)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        try:
            result = await fn(**kwargs)
            if result not in (None, [], {}):
                if use_cache:
                    self.cache.set(cache_key, result, ttl)
                return result
        except Exception as exc:  # noqa: BLE001
            log.warning("Provider[%s].%s 失败: %s", provider.name, method, exc)
        return default

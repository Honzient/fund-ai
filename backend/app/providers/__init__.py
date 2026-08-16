"""数据源包：按配置组装 Provider 注册表。"""
from __future__ import annotations

from app.cache.cache import CacheManager, get_cache
from app.core.config import get_settings
from app.providers.base import DataProvider
from app.providers.custom import CustomDataProvider
from app.providers.eastmoney import EastmoneyProvider
from app.providers.mock_provider import MockProvider
from app.providers.registry import ProviderRegistry


def build_provider_registry(cache: CacheManager | None = None) -> ProviderRegistry:
    settings = get_settings()
    cache = cache or get_cache()
    providers: list[DataProvider] = []
    for name in settings.provider_order:
        if name == "eastmoney":
            providers.append(EastmoneyProvider())
        elif name == "custom":
            providers.append(CustomDataProvider())
        elif name == "mock":
            providers.append(MockProvider())
    if not providers:
        providers = [MockProvider()]
    return ProviderRegistry(providers, cache)


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = build_provider_registry()
    return _registry

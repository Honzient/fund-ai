"""数据源包：按配置组装 Provider 注册表（领域 Provider 拆分）。

- eastmoney       → EastmoneyProvider（基金：搜索/净值/估值/持仓）
- eastmoney-market→ EastmoneyMarketProvider（市场：指数K线/快照）
- eastmoney-macro → EastmoneyMacroProvider（宏观：PMI/CPI 同比，官方发布日期）
- mock            → MockProvider（全部领域演示数据）
- custom          → CustomDataProvider（用户自定义 JSON）
注册表按顺序尝试，空结果自动 fallback。
"""
from __future__ import annotations

from app.cache.cache import CacheManager, get_cache
from app.core.config import get_settings
from app.providers.base import DataProvider
from app.providers.custom import CustomDataProvider
from app.providers.eastmoney import EastmoneyProvider
from app.providers.eastmoney_macro import EastmoneyMacroProvider
from app.providers.eastmoney_market import EastmoneyMarketProvider
from app.providers.mock_provider import MockProvider
from app.providers.registry import ProviderRegistry


def build_provider_registry(cache: CacheManager | None = None) -> ProviderRegistry:
    settings = get_settings()
    cache = cache or get_cache()
    providers: list[DataProvider] = []
    for name in settings.provider_order:
        if name == "eastmoney":
            providers.append(EastmoneyProvider())
            providers.append(EastmoneyMarketProvider())
            providers.append(EastmoneyMacroProvider())
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

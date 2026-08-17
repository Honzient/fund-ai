"""真实宏观 Provider 测试（v0.3）：解析 / 日期 / 去重 / 更新 / fallback / stale / PIT。"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.cache.cache import TTLCache
from app.providers.base import DataProvider, MacroItem
from app.providers.eastmoney_macro import EastmoneyMacroProvider
from app.providers.registry import ProviderRegistry
from app.utils.dates import today


# ---------------------------------------------------------------- 解析

def test_parse_pmi_row():
    """东财 PMI 行 → MacroItem（指标/统计期/发布日期/来源齐全）。"""
    item = EastmoneyMacroProvider._parse_row(  # noqa: SLF001
        "制造业PMI", "MAKE_INDEX", "", "RPT_ECONOMY_PMI",
        {"REPORT_DATE": "2026-07-01 00:00:00", "TIME": "2026年07月份", "MAKE_INDEX": 49.2},
    )
    assert item is not None
    assert item.indicator == "制造业PMI"
    assert item.value == 49.2
    assert item.period == "2026-07"
    assert item.published_at == date(2026, 7, 1)
    assert item.available_at == date(2026, 7, 1)
    assert item.source == "eastmoney"
    assert "RPT_ECONOMY_PMI" in item.source_url


def test_parse_cpi_row():
    """东财 CPI 行：取全国同比（NATIONAL_SAME），单位为 %。"""
    item = EastmoneyMacroProvider._parse_row(  # noqa: SLF001
        "CPI同比", "NATIONAL_SAME", "%", "RPT_ECONOMY_CPI",
        {"REPORT_DATE": "2026-07-01 00:00:00", "TIME": "2026年07月份", "NATIONAL_SAME": 0.5},
    )
    assert item is not None
    assert item.indicator == "CPI同比"
    assert item.value == 0.5
    assert item.unit == "%"


def test_parse_invalid_rows():
    """异常行（缺值/坏日期/坏统计期）→ None，不崩溃。"""
    parse = EastmoneyMacroProvider._parse_row  # noqa: SLF001
    assert parse("制造业PMI", "MAKE_INDEX", "", "R", {"TIME": "2026年07月份"}) is None  # 缺值
    assert parse("制造业PMI", "MAKE_INDEX", "", "R", {"MAKE_INDEX": "abc", "TIME": "2026年07月份"}) is None
    assert parse("制造业PMI", "MAKE_INDEX", "", "R", {"MAKE_INDEX": 50, "TIME": "2026年07月份"}) is None  # 缺日期
    assert parse("制造业PMI", "MAKE_INDEX", "", "R", {"MAKE_INDEX": 50, "REPORT_DATE": "2026-07-01 00:00:00", "TIME": "???"}) is None


def test_period_and_published_separated():
    """统计期（2026-06）与发布日期（2026-07-01）严格分离。"""
    item = EastmoneyMacroProvider._parse_row(  # noqa: SLF001
        "制造业PMI", "MAKE_INDEX", "", "RPT_ECONOMY_PMI",
        {"REPORT_DATE": "2026-07-01 00:00:00", "TIME": "2026年06月份", "MAKE_INDEX": 50.3},
    )
    assert item.period == "2026-06"
    assert item.published_at == date(2026, 7, 1)
    assert item.period != item.published_at.isoformat()[:7]
    assert item.available_at == item.published_at


def test_fetch_series_parses_pages(monkeypatch):
    """_fetch_series：解析接口返回并排序（按 REPORT_DATE 倒序）。"""
    provider = EastmoneyMacroProvider()

    async def fake_get_json(url, params):
        return {
            "result": {
                "data": [
                    {"REPORT_DATE": "2026-07-01 00:00:00", "TIME": "2026年07月份", "MAKE_INDEX": 49.2},
                    {"REPORT_DATE": "2026-06-01 00:00:00", "TIME": "2026年06月份", "MAKE_INDEX": 50.1},
                ]
            }
        }

    monkeypatch.setattr(provider, "_get_json", fake_get_json)
    import asyncio

    items = asyncio.run(provider._fetch_series("RPT_ECONOMY_PMI", "制造业PMI", "MAKE_INDEX", "", 300))  # noqa: SLF001
    assert [i.period for i in items] == ["2026-07", "2026-06"]
    assert [i.value for i in items] == [49.2, 50.1]


# ---------------------------------------------------------------- 同步（去重/更新/质量）

def _macro_items():
    return [
        MacroItem(
            indicator="制造业PMI", value=50.1, unit="", period="2099-11",
            published_at=date(2099, 12, 1), available_at=date(2099, 12, 1),
            source="eastmoney", source_url="https://example.com/pmi",
        ),
        MacroItem(
            indicator="CPI同比", value=2.2, unit="%", period="2099-11",
            published_at=date(2099, 12, 1), available_at=date(2099, 12, 1),
            source="eastmoney", source_url="https://example.com/cpi",
        ),
    ]


class _FakeMacroProvider(DataProvider):
    name = "fake_macro"

    def __init__(self, items):
        self.items = items

    async def get_macro(self, indicator=None, limit=300):
        return self.items

    async def search_funds(self, keyword, limit=20):
        return []

    async def get_fund_info(self, fund_code):
        return None

    async def get_nav_history(self, fund_code, start=None, end=None):
        return []


def _registry_with(items) -> ProviderRegistry:
    return ProviderRegistry([_FakeMacroProvider(items)], TTLCache())


def test_sync_dedupe(db, monkeypatch):
    """同 (indicator, period) 重复同步不重复插入。"""
    from app.models import MacroData
    from app.tasks.pipeline import sync_macro

    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(_macro_items()))
    r1 = sync_macro(db)
    assert r1["new_rows"] == 2
    r2 = sync_macro(db)
    assert r2["new_rows"] == 0 and r2["updated"] == 0
    rows = db.query(MacroData).filter(MacroData.period == "2099-11").count()
    assert rows == 2


def test_sync_update(db, monkeypatch):
    """值变化时更新同一条记录（数据源修正/真实数据覆盖演示数据）。"""
    from app.models import MacroData
    from app.tasks.pipeline import sync_macro

    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(_macro_items()))
    sync_macro(db)
    changed = [
        MacroItem(
            indicator="制造业PMI", value=49.8, unit="", period="2099-11",
            published_at=date(2099, 12, 1), available_at=date(2099, 12, 1),
            source="eastmoney", source_url="https://example.com/pmi-v2",
        )
    ]
    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(changed))
    r = sync_macro(db)
    assert r["new_rows"] == 0 and r["updated"] == 1
    row = (
        db.query(MacroData)
        .filter(MacroData.indicator == "制造业PMI", MacroData.period == "2099-11")
        .first()
    )
    assert row.value == 49.8
    assert row.source_url == "https://example.com/pmi-v2"
    assert row.available_at == date(2099, 12, 1)


def test_sync_saves_provenance(db, monkeypatch):
    """落库完整溯源：source/source_url/published_at/available_at/quality。"""
    from app.models import MacroData
    from app.tasks.pipeline import sync_macro

    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(_macro_items()))
    sync_macro(db)
    row = (
        db.query(MacroData)
        .filter(MacroData.indicator == "CPI同比", MacroData.period == "2099-11")
        .first()
    )
    assert row.source == "eastmoney"
    assert row.source_url == "https://example.com/cpi"
    assert row.published_at == date(2099, 12, 1)
    assert row.available_at == date(2099, 12, 1)


def test_sync_stale_detection(db, monkeypatch):
    """质量分级：60 天内 high / 180 天内 medium / 更早 low。"""
    from app.models import MacroData
    from app.tasks.pipeline import sync_macro

    t = today()
    items = [
        MacroItem(indicator="制造业PMI", value=50.0, period="2098-01",
                  published_at=t - timedelta(days=30), source="eastmoney"),
        MacroItem(indicator="制造业PMI", value=50.1, period="2098-02",
                  published_at=t - timedelta(days=90), source="eastmoney"),
        MacroItem(indicator="制造业PMI", value=50.2, period="2098-03",
                  published_at=t - timedelta(days=400), source="eastmoney"),
    ]
    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(items))
    sync_macro(db)
    q = db.query(MacroData).filter(MacroData.period.in_(["2098-01", "2098-02", "2098-03"]))
    quality = {r.period: r.quality for r in q.all()}
    assert quality["2098-01"] == "high"
    assert quality["2098-02"] == "medium"
    assert quality["2098-03"] == "low"


# ---------------------------------------------------------------- fallback

def test_provider_fallback_to_mock(monkeypatch):
    """东财宏观不可用 → 注册表自动降级 MockProvider。"""
    import asyncio

    from app.providers.mock_provider import MockProvider

    provider = EastmoneyMacroProvider()
    monkeypatch.setattr(provider, "_get_json", lambda url, params: None)  # 接口全挂
    registry = ProviderRegistry([provider, MockProvider()], TTLCache())
    items = asyncio.run(registry.call("get_macro", limit=50, default=[]))
    assert items
    assert all(i.source == "mock" for i in items)


# ---------------------------------------------------------------- Point-in-Time

def test_macro_point_in_time_after_sync(db, monkeypatch):
    """同步后的真实数据按 published_at 截断：T 早于发布日不可见。"""
    from app.prediction.feature_store import FeatureStore
    from app.tasks.pipeline import sync_macro

    items = [
        MacroItem(
            indicator="制造业PMI", value=51.5, unit="", period="2099-02",
            published_at=date(2099, 3, 1), available_at=date(2099, 3, 1),
            source="eastmoney", source_url="https://example.com/pmi",
        )
    ]
    monkeypatch.setattr("app.providers.get_registry", lambda: _registry_with(items))
    sync_macro(db)

    store = FeatureStore()
    series = store._load_macro_series()["macro_pmi"]  # noqa: SLF001
    idx = pd.DatetimeIndex([pd.Timestamp("2099-02-28"), pd.Timestamp("2099-03-02")])
    vals = store._asof_values(idx, series)
    assert vals[0] != pytest.approx(51.5), "发布日之前新值不可见（防未来泄露）"
    assert vals[1] == pytest.approx(51.5), "发布日之后可见"

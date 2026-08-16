"""MockProvider 单元测试：确定性 / 过滤 / 估值时段。"""
import asyncio
from datetime import date, timedelta

import pytest

from app.providers.mock_provider import MOCK_FUNDS, MockProvider


@pytest.fixture()
def provider():
    return MockProvider()


def test_search_filters(provider):
    items = asyncio.run(provider.search_funds("易方达"))
    assert items
    assert all("易方达" in i.fund_name or "易方达" in i.company for i in items)
    by_code = asyncio.run(provider.search_funds("110022"))
    assert any(i.fund_code == "110022" for i in by_code)


def test_nav_history_deterministic(provider):
    a = asyncio.run(provider.get_nav_history("110022"))
    b = asyncio.run(provider.get_nav_history("110022"))
    assert [p.nav for p in a] == [p.nav for p in b]
    dates = [p.date for p in a]
    assert dates == sorted(dates)
    assert len(a) > 500
    assert all(p.daily_return is not None for p in a)
    assert all(p.source == "mock" for p in a)


def test_nav_history_range_filter(provider):
    end = date.today() - timedelta(days=200)
    start = end - timedelta(days=60)
    points = asyncio.run(provider.get_nav_history("110022", start, end))
    assert points
    assert all(start <= p.date <= end for p in points)


def test_fund_info(provider):
    info = asyncio.run(provider.get_fund_info("005827"))
    assert info is not None
    assert info.fund_code == "005827"
    assert info.manager and info.company and info.benchmark
    assert info.latest_nav is not None


def test_holdings(provider):
    items = asyncio.run(provider.get_holdings("161725"))
    assert len(items) == 10
    assert items[0].weight >= items[-1].weight
    assert all(i.industry for i in items)


def test_index_history(provider):
    bars = asyncio.run(provider.get_index_history("000300"))
    assert len(bars) > 500
    assert all(b.high >= b.low for b in bars)


def test_macro_and_news(provider):
    macro = asyncio.run(provider.get_macro())
    assert macro
    indicators = {m.indicator for m in macro}
    assert {"CPI同比", "制造业PMI", "GDP同比"} <= indicators
    news = asyncio.run(provider.get_news(limit=5))
    assert 0 < len(news) <= 5
    assert all(-1 <= n.sentiment <= 1 for n in news)
    policies = asyncio.run(provider.get_policies())
    assert policies
    assert all(p.department and p.importance > 0 for p in policies)

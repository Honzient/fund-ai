"""数据源统一接口。

所有外部数据必须经过 DataProvider 抽象，通过 ProviderRegistry 调用，
失败自动 fallback。新增数据源 = 新增一个 Provider 类，绝不重构系统。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class FundSearchItem:
    fund_code: str
    fund_name: str
    fund_type: str = ""
    company: str = ""
    source: str = ""


@dataclass
class FundInfo:
    fund_code: str
    fund_name: str
    fund_type: str = ""
    manager: str = ""
    company: str = ""
    establish_date: date | None = None
    benchmark: str = ""
    risk_level: str = ""
    management_fee: float | None = None
    purchase_fee: float | None = None
    redemption_fee: float | None = None
    fund_size: float | None = None  # 亿元
    latest_nav: float | None = None
    latest_nav_date: date | None = None
    source: str = ""


@dataclass
class NavPoint:
    date: date
    nav: float
    accumulated_nav: float | None = None
    daily_return: float | None = None  # 小数
    volume: float | None = None
    source: str = ""


@dataclass
class Estimate:
    """盘中估值（非真实净值，仅交易时段内提供）。"""

    fund_code: str
    nav: float
    return_pct: float
    time: datetime
    source: str = ""


@dataclass
class HoldingItem:
    report_date: date
    stock_code: str
    stock_name: str
    weight: float  # 百分比
    industry: str = ""
    market_value: float | None = None  # 亿元
    available_at: date | None = None  # 公众可获得日（真实公告日；无则由服务层按披露时限近似）
    source: str = ""


@dataclass
class IndexBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str = ""


@dataclass
class IndexSnapshot:
    index_code: str
    index_name: str
    market: str = ""
    latest_close: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    data_time: datetime | None = None
    source: str = ""


@dataclass
class MacroItem:
    indicator: str
    value: float
    unit: str = ""
    period: str = ""
    change: float | None = None
    published_at: date | None = None
    source: str = ""


@dataclass
class NewsItem:
    title: str
    content: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime | None = None
    related_fund: str | None = None
    related_industry: str | None = None
    sentiment: float = 0.0
    importance: float = 0.5


@dataclass
class PolicyItem:
    title: str
    content: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime | None = None
    department: str = ""
    policy_type: str = ""
    related_industry: str | None = None
    sentiment: float = 0.0
    impact_score: float = 0.5
    importance: float = 0.5


class DataProvider(ABC):
    """数据源统一接口。实现类必须尽量宽容：网络错误/缺失数据只返回 None 或空列表，由上层 fallback。"""

    name: str = "base"

    @abstractmethod
    async def search_funds(self, keyword: str, limit: int = 20) -> list[FundSearchItem]: ...

    @abstractmethod
    async def get_fund_info(self, fund_code: str) -> FundInfo | None: ...

    @abstractmethod
    async def get_nav_history(
        self, fund_code: str, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]: ...

    async def get_estimate(self, fund_code: str) -> Estimate | None:
        return None

    async def get_holdings(self, fund_code: str, report_date: date | None = None) -> list[HoldingItem]:
        return []

    async def get_index_history(
        self, index_code: str, start: date | None = None, end: date | None = None
    ) -> list[IndexBar]:
        return []

    async def get_index_snapshot(self, index_code: str) -> IndexSnapshot | None:
        return None

    async def get_macro(self, indicator: str | None = None, limit: int = 200) -> list[MacroItem]:
        return []

    async def get_news(self, limit: int = 50) -> list[NewsItem]:
        return []

    async def get_policies(self, limit: int = 50) -> list[PolicyItem]:
        return []

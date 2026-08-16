"""自定义数据源：读取用户提供的 JSON 文件（data/custom/*.json）。

文件格式示例见 data/custom/README.md。用户可将自研数据、私有研究数据
以统一格式放入，系统按同样流程参与分析。所有记录 source="custom"。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.core.config import BASE_DIR
from app.providers.base import (
    DataProvider,
    FundInfo,
    FundSearchItem,
    HoldingItem,
    IndexBar,
    IndexSnapshot,
    MacroItem,
    NavPoint,
    NewsItem,
    PolicyItem,
)
from app.utils.dates import parse_date, parse_datetime

_CUSTOM_DIR = BASE_DIR / "data" / "custom"


class CustomDataProvider(DataProvider):
    name = "custom"

    def __init__(self) -> None:
        self._loaded: dict[str, dict] = {}

    def _load(self) -> dict:
        data: dict = {}
        if _CUSTOM_DIR.exists():
            for f in sorted(_CUSTOM_DIR.glob("*.json")):
                try:
                    with open(f, encoding="utf-8") as fh:
                        loaded = json.load(fh)
                    if isinstance(loaded, dict):
                        for key, value in loaded.items():
                            if key in data:
                                data[key].extend(value if isinstance(value, list) else [value])
                            else:
                                data[key] = list(value) if isinstance(value, list) else [value]
                except Exception:
                    continue
        return data

    async def search_funds(self, keyword: str, limit: int = 20) -> list[FundSearchItem]:
        data = self._load()
        items: list[FundSearchItem] = []
        for f in data.get("funds", []):
            code = str(f.get("fund_code", ""))
            name = str(f.get("fund_name", ""))
            if not keyword or keyword in code or keyword in name:
                items.append(
                    FundSearchItem(
                        fund_code=code, fund_name=name,
                        fund_type=f.get("fund_type", ""), company=f.get("company", ""),
                        source="custom",
                    )
                )
        return items[:limit]

    async def get_fund_info(self, fund_code: str) -> FundInfo | None:
        data = self._load()
        for f in data.get("funds", []):
            if str(f.get("fund_code")) == fund_code:
                return FundInfo(
                    fund_code=fund_code,
                    fund_name=f.get("fund_name", fund_code),
                    fund_type=f.get("fund_type", ""),
                    manager=f.get("manager", ""),
                    company=f.get("company", ""),
                    establish_date=parse_date(f.get("establish_date")),
                    benchmark=f.get("benchmark", ""),
                    risk_level=f.get("risk_level", ""),
                    source="custom",
                )
        return None

    async def get_nav_history(
        self, fund_code: str, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]:
        data = self._load()
        points: list[NavPoint] = []
        for row in data.get("nav", []):
            if str(row.get("fund_code")) != fund_code:
                continue
            d = parse_date(row.get("date"))
            if d is None:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            points.append(
                NavPoint(
                    date=d, nav=float(row["nav"]),
                    accumulated_nav=row.get("accumulated_nav"),
                    daily_return=row.get("daily_return"),
                    volume=row.get("volume"), source="custom",
                )
            )
        points.sort(key=lambda p: p.date)
        return points

    async def get_holdings(self, fund_code: str, report_date: date | None = None) -> list[HoldingItem]:
        data = self._load()
        items: list[HoldingItem] = []
        for row in data.get("holdings", []):
            if str(row.get("fund_code")) != fund_code:
                continue
            items.append(
                HoldingItem(
                    report_date=parse_date(row.get("report_date")) or date.today(),
                    stock_code=str(row.get("stock_code", "")),
                    stock_name=str(row.get("stock_name", "")),
                    weight=float(row.get("weight", 0)),
                    industry=row.get("industry", ""),
                    market_value=row.get("market_value"),
                    source="custom",
                )
            )
        return items

    async def get_index_history(
        self, index_code: str, start: date | None = None, end: date | None = None
    ) -> list[IndexBar]:
        data = self._load()
        bars: list[IndexBar] = []
        for row in data.get("indexes", []):
            if str(row.get("index_code")) != index_code:
                continue
            d = parse_date(row.get("date"))
            if d is None or (start and d < start) or (end and d > end):
                continue
            bars.append(
                IndexBar(
                    date=d, open=float(row.get("open", row.get("close", 0))),
                    high=float(row.get("high", row.get("close", 0))),
                    low=float(row.get("low", row.get("close", 0))),
                    close=float(row.get("close", 0)), volume=row.get("volume"),
                    source="custom",
                )
            )
        bars.sort(key=lambda b: b.date)
        return bars

    async def get_macro(self, indicator: str | None = None, limit: int = 200) -> list[MacroItem]:
        data = self._load()
        items: list[MacroItem] = []
        for row in data.get("macro", []):
            name = str(row.get("indicator", ""))
            if indicator and indicator not in name and name not in indicator:
                continue
            items.append(
                MacroItem(
                    indicator=name, value=float(row.get("value", 0)),
                    unit=row.get("unit", ""), period=str(row.get("period", "")),
                    change=row.get("change"), published_at=parse_date(row.get("published_at")),
                    source="custom",
                )
            )
        return items[-limit:]

    async def get_news(self, limit: int = 50) -> list[NewsItem]:
        data = self._load()
        items: list[NewsItem] = []
        for row in data.get("news", [])[:limit]:
            items.append(
                NewsItem(
                    title=str(row.get("title", "")), content=row.get("content", ""),
                    source=row.get("source", "custom"), url=row.get("url", ""),
                    published_at=parse_datetime(row.get("published_at")),
                    related_fund=row.get("related_fund"), related_industry=row.get("related_industry"),
                    sentiment=float(row.get("sentiment", 0)), importance=float(row.get("importance", 0.5)),
                )
            )
        return items

    async def get_policies(self, limit: int = 50) -> list[PolicyItem]:
        data = self._load()
        items: list[PolicyItem] = []
        for row in data.get("policies", [])[:limit]:
            items.append(
                PolicyItem(
                    title=str(row.get("title", "")), content=row.get("content", ""),
                    source=row.get("source", "custom"), url=row.get("url", ""),
                    published_at=parse_datetime(row.get("published_at")),
                    department=row.get("department", ""), policy_type=row.get("policy_type", ""),
                    related_industry=row.get("related_industry"),
                    sentiment=float(row.get("sentiment", 0)),
                    impact_score=float(row.get("impact_score", 0.5)),
                    importance=float(row.get("importance", 0.5)),
                )
            )
        return items

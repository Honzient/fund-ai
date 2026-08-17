"""Eastmoney 数据中心宏观数据适配层（公开接口，无需 API Key）。

- 制造业 PMI: `RPT_ECONOMY_PMI`（REPORT_DATE=发布日期, TIME=统计期, MAKE_INDEX=制造业PMI）
- CPI 同比:   `RPT_ECONOMY_CPI`（REPORT_DATE=发布日期, TIME=统计期, NATIONAL_SAME=全国同比%）

Point-in-Time 原则：
- `period`（统计期，如 2026-06）与 `published_at`（官方发布日期，如 2026-07-01）严格分离；
- `available_at` = 发布日期（发布即公开）；模型只能在 `available_at <= prediction_time` 时使用。

免责声明：东财数据中心为第三方公开接口，随时可能调整；不可用时由 Provider 注册表
自动降级到 MockProvider，并在界面上显示「最新可用数据」。
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import DataProvider, MacroItem
from app.providers.ratelimit import RateLimiter
from app.utils.dates import parse_date

log = get_logger("app.data")

_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}
_PAGE_SIZE = 100
_MAX_PAGES = 10

# reportName → (指标名, 取值字段, 单位)；指标名与 FeatureStore 的 _MACRO_KEY_MAP 对齐
_MACRO_SERIES: dict[str, tuple[str, str, str]] = {
    "RPT_ECONOMY_PMI": ("制造业PMI", "MAKE_INDEX", ""),
    "RPT_ECONOMY_CPI": ("CPI同比", "NATIONAL_SAME", "%"),
}


class EastmoneyMacroProvider(DataProvider):
    """东财数据中心宏观数据（PMI / CPI 同比，含官方发布日期）。"""

    name = "eastmoney_macro"

    def __init__(self) -> None:
        settings = get_settings()
        self._timeout = settings.PROVIDER_TIMEOUT
        self._max_retries = settings.PROVIDER_MAX_RETRIES
        self._limiter = RateLimiter(settings.PROVIDER_MIN_INTERVAL)
        self._headers = dict(_HEADERS)

    # ------------------------------------------------------------ 领域接口

    async def get_macro(self, indicator: str | None = None, limit: int = 300) -> list[MacroItem]:
        """拉取宏观序列（按 REPORT_DATE 倒序，每指标最近 limit 期）。"""
        items: list[MacroItem] = []
        for report, (name, field, unit) in _MACRO_SERIES.items():
            if indicator and name not in indicator and indicator not in name:
                continue
            items.extend(await self._fetch_series(report, name, field, unit, limit))
        return items

    # ------------------------------------------------------------ 领域 stub（宏观 Provider 不提供）

    async def search_funds(self, keyword: str, limit: int = 20):  # noqa: ARG002
        return []

    async def get_fund_info(self, fund_code: str):  # noqa: ARG002
        return None

    async def get_nav_history(self, fund_code: str, start=None, end=None):  # noqa: ARG002
        return []

    # ------------------------------------------------------------ 拉取与解析

    async def _fetch_series(self, report: str, name: str, field: str, unit: str, limit: int) -> list[MacroItem]:
        out: list[MacroItem] = []
        page = 1
        while len(out) < limit and page <= _MAX_PAGES:
            params = {
                "reportName": report,
                "columns": "ALL",
                "pageNumber": page,
                "pageSize": _PAGE_SIZE,
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
            }
            data = await self._get_json(_API, params)
            if not data:
                break
            rows = ((data.get("result") or {}).get("data")) or []
            if not rows:
                break
            for row in rows:
                item = self._parse_row(name, field, unit, report, row)
                if item is not None:
                    out.append(item)
            if len(rows) < _PAGE_SIZE:
                break
            page += 1
        return out[:limit]

    @staticmethod
    def _parse_row(name: str, field: str, unit: str, report: str, row: dict) -> MacroItem | None:
        """解析东财数据行 → MacroItem（period 与 published_at 分离）。"""
        raw = row.get(field)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        # REPORT_DATE 形如 "2026-07-01 00:00:00"（官方发布日期）
        published = parse_date(str(row.get("REPORT_DATE") or "").split(" ")[0])
        period = EastmoneyMacroProvider._parse_period(str(row.get("TIME") or ""))
        if published is None or period is None:
            return None
        return MacroItem(
            indicator=name,
            value=round(value, 2),
            unit=unit,
            period=period,
            published_at=published,
            available_at=published,  # 发布日当天即公开可用（PIT 截断依据）
            source="eastmoney",
            source_url=f"{_API}?reportName={report}",
        )

    @staticmethod
    def _parse_period(text: str) -> str | None:
        """'2026年07月份' → '2026-07'；'2026年第一季度' → '2026Q1'；无法解析 → None。"""
        import re

        m = re.search(r"(\d{4})年(\d{1,2})月", text)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
        m = re.search(r"(\d{4})年第?([一二三四1-4])季度", text)
        if m:
            q = {"一": 1, "二": 2, "三": 3, "四": 4}.get(m.group(2), m.group(2))
            return f"{m.group(1)}Q{q}"
        return None

    # ------------------------------------------------------------ HTTP

    async def _get_json(self, url: str, params: dict) -> dict | None:
        from app.utils.retry import async_retry

        self._limiter.wait()
        try:
            @async_retry(max_retries=self._max_retries)
            async def _do() -> dict:
                # trust_env=False：绕过系统代理直连（沙箱/部分网络环境系统代理不可用）
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True, trust_env=False
                ) as client:
                    resp = await client.get(url, headers=self._headers, params=params)
                    resp.raise_for_status()
                    return resp.json()

            return await _do()
        except Exception as exc:  # noqa: BLE001 任何异常交给注册表 fallback
            log.warning("Eastmoney 宏观请求失败 %s: %s", url, exc)
            return None

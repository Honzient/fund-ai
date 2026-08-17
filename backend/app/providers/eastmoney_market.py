"""Eastmoney 市场指数领域 Provider（从基金 Provider 拆分，职责分离）。

指数K线 / 指数快照；共享基类的 HTTP/限流/重试基础设施。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.providers.base import IndexBar, IndexSnapshot
from app.providers.eastmoney import EastmoneyProvider, _INDEX_NAMES, _INDEX_SECID
from app.utils.dates import parse_date


class EastmoneyMarketProvider(EastmoneyProvider):
    name = "eastmoney-market"

    # ------------------------------------------------------------ 基金方法禁用（本 Provider 只负责市场）

    async def search_funds(self, keyword: str, limit: int = 20):  # noqa: ARG002
        return []

    async def get_fund_info(self, fund_code: str):  # noqa: ARG002
        return None

    async def get_nav_history(self, fund_code: str, start=None, end=None):  # noqa: ARG002
        return []

    async def get_holdings(self, fund_code: str, report_date=None):  # noqa: ARG002
        return []

    async def get_estimate(self, fund_code: str):  # noqa: ARG002
        return None

    # ------------------------------------------------------------ 指数

    async def get_index_history(
        self, index_code: str, start: date | None = None, end: date | None = None
    ) -> list[IndexBar]:
        secid = _INDEX_SECID.get(index_code)
        if not secid:
            return []
        beg = (start or date.today() - timedelta(days=365 * 3)).strftime("%Y%m%d")
        end_s = (end or date.today()).strftime("%Y%m%d")
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        data = await self._get_json(
            url,
            params={
                "secid": secid, "klt": "101", "fqt": "1",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "beg": beg, "end": end_s,
            },
        )
        klines = ((data or {}).get("data") or {}).get("klines") or []
        bars: list[IndexBar] = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            try:
                bars.append(
                    IndexBar(
                        date=parse_date(parts[0]) or date.today(),
                        open=float(parts[1]), close=float(parts[2]),
                        high=float(parts[3]), low=float(parts[4]),
                        volume=float(parts[5]) if parts[5] else None,
                        source="eastmoney",
                    )
                )
            except (ValueError, IndexError):
                continue
        return bars

    async def get_index_snapshot(self, index_code: str) -> IndexSnapshot | None:
        secid = _INDEX_SECID.get(index_code)
        if not secid:
            return None
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        data = await self._get_json(
            url, params={"secid": secid, "fields": "f43,f44,f45,f46,f60,f170,f86"}
        )
        row = (data or {}).get("data") or {}
        if not row:
            return None
        try:
            # push2 行情字段为整数放大值（×100），先缩放再计算
            close = float(row.get("f43") or 0) / 100.0
            prev_close = float(row.get("f60") or 0) / 100.0
            change = round(close - prev_close, 4)
            change_pct = round((close / prev_close - 1) * 100, 4) if prev_close else 0.0
            ts = row.get("f86")
            data_time = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else datetime.now(timezone.utc)
            )
        except (TypeError, ValueError):
            return None
        return IndexSnapshot(
            index_code=index_code,
            index_name=_INDEX_NAMES.get(index_code, index_code),
            market="US" if index_code in ("NDX", "SPX") else ("HK" if index_code == "HSI" else "CN"),
            latest_close=close, change=change, change_pct=change_pct,
            data_time=data_time, source="eastmoney",
        )

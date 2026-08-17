"""Eastmoney（天天基金/东方财富）公开接口适配层。

数据来源（公开接口，无需 API Key）：
- 基金搜索:   fundsuggest.eastmoney.com  FundSearchAPI
- 基金净值:   fund.eastmoney.com/pingzhongdata/{code}.js
- 基金元数据: fundmobapi.eastmoney.com FundMNDetailInformation
- 盘中估值:   fundmobapi.eastmoney.com FundMNFInfo（GSZ/GSZZL，仅交易时段）
- 基金持仓:   fundf10.eastmoney.com FundArchivesDatas
- 指数K线:    push2his.eastmoney.com kline API
- 指数快照:   push2.eastmoney.com stock/get

免责声明：以上为第三方公开接口，随时可能调整；不可用时系统自动降级到
MockProvider，并在界面上显示「最新可用数据」。本层处理超时/重试/限流/解析容错。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import (
    DataProvider,
    Estimate,
    FundInfo,
    FundSearchItem,
    HoldingItem,
    IndexBar,
    IndexSnapshot,
    NavPoint,
)
from app.providers.ratelimit import RateLimiter
from app.utils.dates import parse_date, parse_datetime
from app.utils.retry import async_retry

log = get_logger("app.data")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_INDEX_SECID = {
    "000300": "1.000300", "000905": "1.000905", "000852": "1.000852",
    "000001": "1.000001", "399006": "0.399006",
    "NDX": "100.NDX", "SPX": "100.SPX", "HSI": "100.HSI",
}

_INDEX_NAMES = {
    "000300": "沪深300", "000905": "中证500", "000852": "中证1000",
    "000001": "上证指数", "399006": "创业板指",
    "NDX": "纳斯达克100", "SPX": "标普500", "HSI": "恒生指数",
}

# 常见个股行业映射（用于持仓行业暴露；未知个股标注"其他"）
_STOCK_INDUSTRY = {
    "600519": "食品饮料", "000858": "食品饮料", "000568": "食品饮料", "600809": "食品饮料",
    "002304": "食品饮料", "000596": "食品饮料", "603369": "食品饮料", "600779": "食品饮料",
    "600702": "食品饮料", "000799": "食品饮料", "603288": "食品饮料", "600887": "食品饮料",
    "600872": "食品饮料", "000333": "家用电器", "600690": "家用电器",
    "601318": "非银金融", "600036": "银行", "600030": "非银金融", "300059": "非银金融",
    "600276": "医药生物", "300760": "医药生物", "603259": "医药生物", "300015": "医药生物",
    "300347": "医药生物", "600436": "医药生物", "000538": "医药生物", "300122": "医药生物",
    "688235": "医药生物", "002821": "医药生物", "300142": "医药生物",
    "300750": "电力设备", "601012": "电力设备", "300274": "电力设备", "300014": "电力设备",
    "002475": "电子", "002415": "电子", "603501": "电子", "603986": "电子",
    "002371": "电子", "688012": "电子", "688981": "电子", "002049": "电子",
    "300661": "电子", "300782": "电子", "300124": "机械设备",
    "601888": "商贸零售", "002714": "农林牧渔",
    "00700": "互联网", "09988": "互联网", "09987": "互联网", "03690": "互联网",
    "09618": "互联网", "09999": "互联网", "09888": "互联网", "09961": "互联网",
    "09626": "互联网", "01024": "互联网", "02331": "纺织服饰", "PDD": "互联网",
}


def _extract_jsonp(text: str, key: str) -> Any | None:
    if not text:
        return None
    idx = text.find(key)
    if idx < 0:
        return None
    start = text.find("{", idx)
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _extract_js_array(text: str, var_name: str) -> list[Any] | None:
    if not text:
        return None
    pattern = re.compile(var_name + r"\s*=\s*(\[.*?\])\s*;", re.S)
    m = pattern.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


class EastmoneyProvider(DataProvider):
    name = "eastmoney"

    def __init__(self) -> None:
        settings = get_settings()
        self._timeout = settings.PROVIDER_TIMEOUT
        self._max_retries = settings.PROVIDER_MAX_RETRIES
        self._limiter = RateLimiter(settings.PROVIDER_MIN_INTERVAL)
        self._base_headers = dict(_HEADERS)

    async def _get(self, url: str, headers: dict | None = None, params: dict | None = None) -> httpx.Response:
        self._limiter.wait()  # 线程安全时间锁（同步调用，避免跨事件循环问题）
        h = dict(self._base_headers)
        if headers:
            h.update(headers)

        @async_retry(max_retries=self._max_retries)
        async def _do() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=h, params=params)
                resp.raise_for_status()
                return resp

        return await _do()

    async def _get_json(self, url: str, params: dict | None = None) -> dict | None:
        """GET + JSON 解析；接口返回「网络繁忙」类业务错误时重试后放弃（由上层降级）。"""
        import asyncio as _asyncio

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._get(url, params=params)
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await _asyncio.sleep(0.6 * (attempt + 1))
                continue
            if isinstance(data, dict) and data.get("Success") is False:
                last_error = RuntimeError(f"业务错误 ErrCode={data.get('ErrCode')} {data.get('ErrMsg')}")
                await _asyncio.sleep(0.8 * (attempt + 1))
                continue
            return data
        log.warning("Eastmoney JSON 请求失败 %s: %s", url, last_error)
        return None

    # ------------------------------------------------------------ 基金

    async def search_funds(self, keyword: str, limit: int = 20) -> list[FundSearchItem]:
        if not keyword:
            return []
        url = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
        try:
            resp = await self._get(url, params={"m": "1", "key": keyword})
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("Eastmoney 基金搜索失败: %s", exc)
            return []
        items: list[FundSearchItem] = []
        for row in (data.get("Datas") or [])[:limit]:
            code = str(row.get("CODE", ""))
            if not re.fullmatch(r"\d{6}", code):
                continue
            base = row.get("FundBaseInfo") or {}
            items.append(
                FundSearchItem(
                    fund_code=code,
                    fund_name=re.sub(r"<[^>]+>", "", row.get("NAME", "")),
                    fund_type=base.get("FTYPE", ""),
                    company=base.get("JJGS", ""),
                    source="eastmoney",
                )
            )
        return items

    async def _pingzhong(self, fund_code: str) -> str:
        url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        try:
            resp = await self._get(url, headers={"Referer": "https://fund.eastmoney.com/"})
            return resp.text
        except Exception as exc:  # noqa: BLE001
            log.warning("Eastmoney 净值数据请求失败 %s: %s", fund_code, exc)
            return ""

    async def _fund_detail_api(self, fund_code: str) -> dict:
        """基金详情（类型/公司/经理/成立日/基准/最新净值）。"""
        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNDetailInformation"
        data = await self._get_json(
            url,
            params={
                "FCODE": fund_code, "deviceid": "1", "plat": "Iphone",
                "product": "EFund", "version": "6.3.8",
            },
        )
        return (data or {}).get("Datas") or {}

    async def get_fund_info(self, fund_code: str) -> FundInfo | None:
        detail = await self._fund_detail_api(fund_code)
        if not detail:
            return None
        navs = await self.get_nav_history(fund_code)
        latest = navs[-1] if navs else None

        def _f(key: str) -> float | None:
            try:
                return float(detail.get(key)) if detail.get(key) not in (None, "") else None
            except (TypeError, ValueError):
                return None

        name = detail.get("SHORTNAME") or detail.get("FULLNAME") or fund_code
        return FundInfo(
            fund_code=fund_code,
            fund_name=str(name),
            fund_type=detail.get("FTYPE", ""),
            manager=str(detail.get("JJJL") or ""),
            company=str(detail.get("JJGS") or ""),
            establish_date=parse_date(str(detail.get("ESTABDATE") or "")),
            benchmark=str(detail.get("BENCH") or ""),
            risk_level=str(detail.get("RISKLEVEL") or ""),
            management_fee=_f("MGREXP"),
            purchase_fee=_f("SALESEXP"),
            redemption_fee=None,
            fund_size=_f("FEATURE"),
            latest_nav=latest.nav if latest else _f("NETNAV"),
            latest_nav_date=latest.date if latest else parse_date(str(detail.get("FEGMRQ") or "")),
            source="eastmoney",
        )

    async def get_nav_history(
        self, fund_code: str, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]:
        text = await self._pingzhong(fund_code)
        if not text:
            return []
        net = _extract_js_array(text, "Data_netWorthTrend") or []
        ac_map: dict[str, float] = {}
        for row in _extract_js_array(text, "Data_ACWorthTrend") or []:
            try:
                if isinstance(row, list) and len(row) >= 2:
                    ts, val = int(row[0]), float(row[1])
                elif isinstance(row, dict) and row.get("x"):
                    ts, val = int(row["x"]), float(row.get("y") or 0.0)
                else:
                    continue
                d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
                ac_map[d.isoformat()] = val
            except Exception:  # noqa: BLE001
                continue
        points: list[NavPoint] = []
        for row in net:
            if not isinstance(row, dict):
                continue
            try:
                d = datetime.fromtimestamp(int(row["x"]) / 1000, tz=timezone.utc).date()
                nav = float(row.get("y") or 0.0)
            except Exception:  # noqa: BLE001
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            eq = row.get("equityReturn")
            daily_return = float(eq) / 100.0 if eq not in (None, "") else None
            points.append(
                NavPoint(
                    date=d, nav=nav,
                    accumulated_nav=ac_map.get(d.isoformat()),
                    daily_return=daily_return, volume=None, source="eastmoney",
                )
            )
        return points

    async def get_estimate(self, fund_code: str) -> Estimate | None:
        """盘中估值（仅交易时段内 GSZ 非空）。"""
        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo"
        data = await self._get_json(
            url,
            params={
                "pageIndex": "1", "pageSize": "10", "plat": "Android",
                "appType": "ttjj", "product": "EFund", "Version": "1",
                "deviceid": "1", "Fcodes": fund_code,
            },
        )
        if not data:
            return None
        rows = data.get("Datas") or []
        if not rows:
            return None
        row = rows[0]
        gsz = row.get("GSZ")
        if gsz in (None, ""):
            return None
        try:
            t = parse_datetime(str(row.get("GZTIME")))
        except Exception:  # noqa: BLE001
            t = None
        return Estimate(
            fund_code=fund_code,
            nav=float(gsz),
            return_pct=float(row.get("GSZZL") or 0.0),
            time=t or datetime.now(timezone.utc),
            source="eastmoney-estimate",
        )

    async def get_holdings(self, fund_code: str, report_date: date | None = None) -> list[HoldingItem]:
        year = report_date.year if report_date else datetime.now().year
        month = report_date.month if report_date else datetime.now().month
        url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
        try:
            resp = await self._get(
                url,
                headers={"Referer": f"https://fundf10.eastmoney.com/jjcc_{fund_code}.html"},
                params={"type": "jjcc", "code": fund_code, "topline": "10", "year": year, "month": month},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Eastmoney 持仓请求失败 %s: %s", fund_code, exc)
            return []
        text = resp.text
        start = text.find('content:"')
        end = text.find("arryear", start)
        if start < 0 or end < 0:
            return []
        segment = text[start + 9 : end]
        if segment.endswith('",'):
            segment = segment[:-2]
        try:
            html = json.loads('"' + segment + '"')
        except Exception:  # noqa: BLE001
            return []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        items: list[HoldingItem] = []
        for row in rows[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) < 7:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            code = clean[1]
            if not re.fullmatch(r"\d{5,6}", code):
                continue
            try:
                weight = float(clean[6].replace("%", ""))
            except ValueError:
                continue
            mv = None
            if len(clean) >= 9:
                try:
                    mv = float(clean[8].replace(",", "")) / 10000.0  # 万元 → 亿元
                except ValueError:
                    mv = None
            items.append(
                HoldingItem(
                    report_date=date(year, month, 28),
                    stock_code=code,
                    stock_name=clean[2],
                    weight=weight,
                    industry=_STOCK_INDUSTRY.get(code, "unknown"),
                    market_value=mv,
                    source="eastmoney",
                )
            )
        return items


    # ------------------------------------------------------------ 辅助解析

    @staticmethod
    def _var_string(text: str, var: str) -> str:
        m = re.search(var + r'\s*=\s*"(.*?)"', text)
        return m.group(1) if m else ""

    @staticmethod
    def _var_float(text: str, var: str) -> float | None:
        m = re.search(var + r'\s*=\s*"([\d.]+)"', text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None


# 指数接口已拆分至 eastmoney_market.EastmoneyMarketProvider（领域 Provider 职责分离）

"""Mock 数据源：离线演示数据（确定性生成，source="mock"）。

用途：
1. 无网络 / 真实数据源不可用时的完整降级方案；
2. 单元测试与演示环境的稳定数据基础。

所有数据均明确标记 source="mock"，前端必须显示「最新可用数据」而非伪装实时。
"""
from __future__ import annotations

import math
import zlib
from datetime import date, datetime, time, timedelta, timezone

import numpy as np

from app.core.config import get_settings
from app.providers.base import (
    DataProvider,
    Estimate,
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
from app.utils.dates import last_trading_day, parse_date, utcnow

_TZ_CN = timezone(timedelta(hours=8))

# ---------------------------------------------------------------- 目录数据

MOCK_FUNDS: list[dict] = [
    dict(code="000001", name="华夏成长混合", type="混合型", company="华夏基金", manager="刘欣",
         benchmark="沪深300指数", risk_level="中高", fees=(1.50, 0.15, 0.50), size=42.6,
         establish="2001-12-18", industry="综合", start_nav=1.08, drift=0.00022, vol=0.012),
    dict(code="110022", name="易方达消费行业股票", type="股票型", company="易方达基金", manager="萧楠",
         benchmark="中证主要消费指数", risk_level="高", fees=(1.50, 0.15, 0.50), size=180.4,
         establish="2010-08-20", industry="食品饮料", start_nav=3.62, drift=0.00030, vol=0.015),
    dict(code="005827", name="易方达蓝筹精选混合", type="混合型", company="易方达基金", manager="张坤",
         benchmark="沪深300指数", risk_level="高", fees=(1.50, 0.15, 0.50), size=320.1,
         establish="2018-09-05", industry="食品饮料", start_nav=2.35, drift=0.00026, vol=0.014),
    dict(code="003096", name="中欧医疗健康混合A", type="混合型", company="中欧基金", manager="葛兰",
         benchmark="中证医药卫生指数", risk_level="高", fees=(1.50, 0.15, 0.50), size=210.8,
         establish="2016-09-29", industry="医药生物", start_nav=1.92, drift=0.00010, vol=0.017),
    dict(code="161725", name="招商中证白酒指数(LOF)A", type="指数型", company="招商基金", manager="侯昊",
         benchmark="中证白酒指数", risk_level="高", fees=(1.00, 0.10, 0.50), size=260.5,
         establish="2015-05-27", industry="食品饮料", start_nav=1.05, drift=0.00012, vol=0.019),
    dict(code="260108", name="景顺长城新兴成长混合A", type="混合型", company="景顺长城基金", manager="刘彦春",
         benchmark="沪深300指数", risk_level="高", fees=(1.50, 0.15, 0.50), size=280.0,
         establish="2006-06-28", industry="食品饮料", start_nav=2.02, drift=0.00020, vol=0.014),
    dict(code="519674", name="银河创新成长混合A", type="混合型", company="银河基金", manager="郑巍山",
         benchmark="中证800成长指数", risk_level="高", fees=(1.50, 0.15, 0.50), size=95.3,
         establish="2010-12-29", industry="电子", start_nav=4.12, drift=0.00035, vol=0.021),
    dict(code="001593", name="天弘创业板ETF联接A", type="指数型", company="天弘基金", manager="林心龙",
         benchmark="创业板指数", risk_level="高", fees=(0.50, 0.10, 0.50), size=88.7,
         establish="2015-07-08", industry="综合", start_nav=0.98, drift=0.00018, vol=0.016),
    dict(code="000032", name="易方达信用债债券A", type="债券型", company="易方达基金", manager="胡剑",
         benchmark="中债综合指数", risk_level="中低", fees=(0.70, 0.08, 0.10), size=120.2,
         establish="2013-04-24", industry="债券", start_nav=1.62, drift=0.00006, vol=0.002),
    dict(code="006327", name="易方达中证海外中国互联网50ETF联接A", type="QDII", company="易方达基金",
         manager="范冰", benchmark="中证海外中国互联网50指数", risk_level="高",
         fees=(0.60, 0.10, 0.50), size=56.9, establish="2019-01-18", industry="互联网",
         start_nav=1.15, drift=0.00010, vol=0.020),
]

MOCK_HOLDINGS: dict[str, list[tuple[str, str, float, str]]] = {
    "000001": [("600519", "贵州茅台", 6.2, "食品饮料"), ("601318", "中国平安", 4.8, "非银金融"),
               ("600036", "招商银行", 4.1, "银行"), ("000858", "五粮液", 3.6, "食品饮料"),
               ("600276", "恒瑞医药", 3.2, "医药生物"), ("300750", "宁德时代", 3.0, "电力设备"),
               ("601012", "隆基绿能", 2.6, "电力设备"), ("600030", "中信证券", 2.4, "非银金融"),
               ("000333", "美的集团", 2.2, "家用电器"), ("601888", "中国中免", 2.0, "商贸零售")],
    "110022": [("600519", "贵州茅台", 9.8, "食品饮料"), ("000858", "五粮液", 9.2, "食品饮料"),
               ("600887", "伊利股份", 7.5, "食品饮料"), ("000568", "泸州老窖", 6.8, "食品饮料"),
               ("603288", "海天味业", 5.4, "食品饮料"), ("000333", "美的集团", 4.9, "家用电器"),
               ("600690", "海尔智家", 4.2, "家用电器"), ("600809", "山西汾酒", 3.8, "食品饮料"),
               ("002714", "牧原股份", 3.1, "农林牧渔"), ("600872", "中炬高新", 2.6, "食品饮料")],
    "005827": [("600519", "贵州茅台", 9.5, "食品饮料"), ("000858", "五粮液", 9.0, "食品饮料"),
               ("00700", "腾讯控股", 8.2, "互联网"), ("03690", "美团-W", 6.4, "互联网"),
               ("000568", "泸州老窖", 5.6, "食品饮料"), ("600036", "招商银行", 4.5, "银行"),
               ("601318", "中国平安", 3.8, "非银金融"), ("600809", "山西汾酒", 3.4, "食品饮料"),
               ("600887", "伊利股份", 2.9, "食品饮料"), ("02331", "李宁", 2.5, "纺织服饰")],
    "003096": [("600276", "恒瑞医药", 9.6, "医药生物"), ("300760", "迈瑞医疗", 8.8, "医药生物"),
               ("603259", "药明康德", 7.9, "医药生物"), ("300015", "爱尔眼科", 6.5, "医药生物"),
               ("300347", "泰格医药", 5.2, "医药生物"), ("600436", "片仔癀", 4.8, "医药生物"),
               ("000538", "云南白药", 4.1, "医药生物"), ("300122", "智飞生物", 3.6, "医药生物"),
               ("688235", "百济神州", 3.2, "医药生物"), ("002821", "凯莱英", 2.8, "医药生物")],
    "161725": [("600519", "贵州茅台", 14.6, "食品饮料"), ("000858", "五粮液", 13.8, "食品饮料"),
               ("000568", "泸州老窖", 10.5, "食品饮料"), ("600809", "山西汾酒", 9.6, "食品饮料"),
               ("002304", "洋河股份", 8.2, "食品饮料"), ("000596", "古井贡酒", 5.4, "食品饮料"),
               ("603369", "今世缘", 3.8, "食品饮料"), ("600779", "水井坊", 2.6, "食品饮料"),
               ("600702", "舍得酒业", 2.2, "食品饮料"), ("000799", "酒鬼酒", 1.8, "食品饮料")],
    "260108": [("600519", "贵州茅台", 9.4, "食品饮料"), ("000858", "五粮液", 8.6, "食品饮料"),
               ("000568", "泸州老窖", 6.9, "食品饮料"), ("601888", "中国中免", 5.2, "商贸零售"),
               ("603288", "海天味业", 4.8, "食品饮料"), ("600809", "山西汾酒", 4.1, "食品饮料"),
               ("002304", "洋河股份", 3.5, "食品饮料"), ("600887", "伊利股份", 3.0, "食品饮料"),
               ("000333", "美的集团", 2.6, "家用电器"), ("600690", "海尔智家", 2.2, "家用电器")],
    "519674": [("002475", "立讯精密", 9.2, "电子"), ("002415", "海康威视", 8.4, "电子"),
               ("603501", "韦尔股份", 7.1, "电子"), ("603986", "兆易创新", 6.3, "电子"),
               ("002371", "北方华创", 5.8, "电子"), ("688012", "中微公司", 4.9, "电子"),
               ("688981", "中芯国际", 4.2, "电子"), ("002049", "紫光国微", 3.5, "电子"),
               ("300661", "圣邦股份", 2.9, "电子"), ("300782", "卓胜微", 2.4, "电子")],
    "001593": [("300750", "宁德时代", 12.4, "电力设备"), ("300059", "东方财富", 7.8, "非银金融"),
               ("300760", "迈瑞医疗", 5.6, "医药生物"), ("300124", "汇川技术", 4.2, "机械设备"),
               ("300015", "爱尔眼科", 3.5, "医药生物"), ("300274", "阳光电源", 3.1, "电力设备"),
               ("300014", "亿纬锂能", 2.7, "电力设备"), ("300122", "智飞生物", 2.4, "医药生物"),
               ("300782", "卓胜微", 2.1, "电子"), ("300142", "沃森生物", 1.9, "医药生物")],
    "000032": [("250015", "16国开债", 8.5, "债券"), ("220006", "22附息国债", 7.8, "债券"),
               ("210203", "21进出债", 6.9, "债券"), ("230016", "23附息国债", 6.2, "债券"),
               ("240006", "24附息国债", 5.5, "债券"), ("200207", "20国开债", 4.8, "债券"),
               ("190209", "19国开债", 4.1, "债券"), ("180204", "18国开债", 3.4, "债券"),
               ("170210", "17国开债", 2.8, "债券"), ("160210", "16国开债", 2.2, "债券")],
    "006327": [("00700", "腾讯控股", 18.5, "互联网"), ("09988", "阿里巴巴-SW", 15.2, "互联网"),
               ("03690", "美团-W", 11.8, "互联网"), ("PDD", "拼多多", 9.6, "互联网"),
               ("09618", "京东集团-SW", 7.2, "互联网"), ("09999", "网易-S", 5.8, "互联网"),
               ("09888", "百度集团-SW", 4.6, "互联网"), ("09961", "携程集团-S", 3.8, "互联网"),
               ("09626", "哔哩哔哩-W", 2.9, "互联网"), ("01024", "快手-W", 2.4, "互联网")],
}

MOCK_INDEXES: list[dict] = [
    dict(code="000300", name="沪深300", market="CN", base=3850.0, drift=0.00008, vol=0.010),
    dict(code="000905", name="中证500", market="CN", base=5650.0, drift=0.00006, vol=0.012),
    dict(code="000852", name="中证1000", market="CN", base=6200.0, drift=0.00005, vol=0.014),
    dict(code="000001", name="上证指数", market="CN", base=3320.0, drift=0.00007, vol=0.009),
    dict(code="399006", name="创业板指", market="CN", base=2120.0, drift=0.00009, vol=0.015),
    dict(code="NDX", name="纳斯达克100", market="US", base=20800.0, drift=0.00018, vol=0.012),
    dict(code="SPX", name="标普500", market="US", base=5650.0, drift=0.00015, vol=0.009),
    dict(code="HSI", name="恒生指数", market="HK", base=18800.0, drift=0.00006, vol=0.013),
]

_MACRO_BASE = [
    ("CPI同比", 2.1, "%", 0.35),
    ("PPI同比", -1.6, "%", 0.6),
    ("制造业PMI", 50.1, "", 1.1),
    ("GDP同比", 5.1, "%", 0.35),
    ("M2同比", 8.1, "%", 0.7),
    ("社会融资规模", 3.2, "万亿元", 1.7),
    ("1年期LPR", 3.35, "%", 0.12),
    ("美元兑人民币", 7.16, "", 0.13),
    ("10年期国债收益率", 2.35, "%", 0.22),
    ("城镇调查失业率", 5.1, "%", 0.14),
    ("布伦特原油", 82.0, "美元/桶", 7.5),
    ("COMEX黄金", 2380.0, "美元/盎司", 150.0),
]

_MOCK_NEWS: list[dict] = [
    ("央行开展MLF操作维护流动性合理充裕", "金融", 0.5, 0.8, "宏观流动性保持合理充裕，利好权益市场情绪。"),
    ("国常会部署扩大内需促进消费政策", "消费", 0.7, 0.85, "消费刺激政策预期升温，利好食品饮料与家电板块。"),
    ("新能源车企7月交付量普遍超预期", "新能源", 0.6, 0.7, "行业景气度回升，利好新能源产业链。"),
    ("半导体设备国产化率持续提升", "半导体", 0.6, 0.75, "国产替代逻辑强化，利好电子行业。"),
    ("多家药企创新药获批上市", "医药生物", 0.5, 0.7, "创新药管线兑现，利好医药板块。"),
    ("白酒渠道库存去化好于预期", "食品饮料", 0.55, 0.7, "高端白酒动销改善，利好消费基金。"),
    ("美联储官员释放鸽派信号", "海外", 0.4, 0.7, "海外流动性预期改善，利好成长风格。"),
    ("二手房成交量环比回落", "房地产", -0.4, 0.65, "地产景气度仍有压力，注意相关敞口。"),
    ("国际油价小幅回落", "能源", -0.2, 0.5, "大宗商品价格波动，影响能源产业链。"),
    ("两融余额连续三日回升", "金融", 0.4, 0.6, "市场风险偏好回升。"),
    ("创业板指成分股回购增持增多", "综合", 0.35, 0.55, "产业资本增持释放积极信号。"),
    ("人民币汇率保持基本稳定", "金融", 0.3, 0.6, "汇率稳定有利于外资流入。"),
    ("某科技龙头发布新一代大模型", "人工智能", 0.55, 0.75, "AI 产业趋势延续，利好科技板块。"),
    ("公募基金二季报显示权益仓位回升", "金融", 0.4, 0.65, "机构资金风险偏好改善。"),
    ("医药集采常态化推进", "医药生物", -0.3, 0.65, "集采压价持续，医药板块存在结构性分化。"),
    ("央行发布二季度货币政策执行报告", "金融", 0.35, 0.8, "货币政策延续稳健，强调结构性工具。"),
    ("多地出台人工智能产业扶持政策", "人工智能", 0.6, 0.8, "政策加码 AI 产业，利好相关赛道。"),
    ("消费数据改善 社零增速回升", "消费", 0.55, 0.75, "消费复苏动能增强。"),
    ("部分QDII基金溢价率回落", "海外", 0.0, 0.5, "海外资产价格波动，注意溢价风险。"),
    ("债市收益率小幅上行", "债券", -0.25, 0.55, "利率小幅上行，债基净值或承压。"),
]

_MOCK_POLICIES: list[dict] = [
    ("新能源汽车购置税减免政策延续至2027年底", "财政部", "产业政策", "新能源", 0.7, 0.8, 0.85,
     "延续购置税减免，稳定新能源汽车消费预期。"),
    ("国家数据局发布数据要素市场化配置改革方案", "国家数据局", "产业政策", "人工智能", 0.65, 0.75, 0.8,
     "数据要素改革提速，利好数字经济相关行业。"),
    ("证监会发布深化资本市场改革措施", "证监会", "资本市场", "金融", 0.6, 0.7, 0.8,
     "活跃资本市场、提振投资者信心，利好券商与市场情绪。"),
    ("医药集中采购常态化制度化文件印发", "国家医保局", "监管政策", "医药生物", -0.35, 0.6, 0.75,
     "集采常态化对部分仿制药企形成压力，创新药影响相对有限。"),
    ("央行下调存款准备金率0.25个百分点", "中国人民银行", "货币政策", "金融", 0.65, 0.75, 0.85,
     "释放长期流动性约5000亿元，利好市场风险偏好。"),
    ("人工智能+行动实施方案发布", "工信部", "产业政策", "人工智能", 0.7, 0.8, 0.85,
     "推动 AI 与制造业融合，利好半导体、算力、软件行业。"),
    ("促进家居消费若干措施出台", "商务部", "消费政策", "消费", 0.5, 0.6, 0.7,
     "家居消费补贴政策落地，利好家电与家居产业链。"),
    ("房地产融资协调机制进一步落地", "住建部", "产业政策", "房地产", 0.35, 0.55, 0.7,
     "地产融资环境边际改善，但基本面修复仍需观察。"),
    ("半导体产业高质量发展指导意见发布", "工信部", "产业政策", "半导体", 0.68, 0.75, 0.8,
     "国产替代政策加码，利好半导体设备与材料。"),
    ("双碳目标下新型储能发展实施方案", "国家发改委", "产业政策", "新能源", 0.6, 0.7, 0.75,
     "储能装机目标上调，利好新能源产业链。"),
    ("跨境电商综合试验区扩围", "商务部", "外贸政策", "消费", 0.4, 0.5, 0.6,
     "跨境电商支持政策加码，利好外贸与物流。"),
    ("存款利率自律机制下调", "市场利率定价自律机制", "货币政策", "金融", 0.5, 0.6, 0.7,
     "存款利率下调有助于降低银行负债成本，利好债市。"),
    ("科技创新再贷款额度增加", "中国人民银行", "货币政策", "半导体", 0.55, 0.65, 0.7,
     "定向支持科技企业融资，利好成长风格。"),
    ("平台经济常态化监管指引发布", "市场监管总局", "监管政策", "互联网", 0.25, 0.5, 0.65,
     "监管框架明确化，互联网平台预期趋于稳定。"),
    ("汽车以旧换新补贴细则落地", "商务部", "消费政策", "新能源", 0.6, 0.65, 0.7,
     "以旧换新补贴刺激汽车消费，利好整车与零部件。"),
]


def _rng_for(seed_text: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(seed_text.encode("utf-8")))


def _business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


class MockProvider(DataProvider):
    name = "mock"

    def __init__(self) -> None:
        self._nav_cache: dict[str, list[NavPoint]] = {}
        self._index_cache: dict[str, list[IndexBar]] = {}
        self._years = 3.6
        self._end_date = last_trading_day()

    # ------------------------------------------------------------ 基金

    async def search_funds(self, keyword: str, limit: int = 20) -> list[FundSearchItem]:
        keyword = (keyword or "").strip()
        results: list[FundSearchItem] = []
        for f in MOCK_FUNDS:
            if not keyword or keyword in f["code"] or keyword in f["name"] or keyword in f["company"]:
                results.append(
                    FundSearchItem(
                        fund_code=f["code"], fund_name=f["name"], fund_type=f["type"],
                        company=f["company"], source="mock",
                    )
                )
        return results[:limit]

    async def get_fund_info(self, fund_code: str) -> FundInfo | None:
        for f in MOCK_FUNDS:
            if f["code"] == fund_code:
                navs = await self.get_nav_history(fund_code)
                latest = navs[-1] if navs else None
                mgmt, purch, redem = f["fees"]
                return FundInfo(
                    fund_code=f["code"], fund_name=f["name"], fund_type=f["type"],
                    manager=f["manager"], company=f["company"],
                    establish_date=parse_date(f["establish"]),
                    benchmark=f["benchmark"], risk_level=f["risk_level"],
                    management_fee=mgmt, purchase_fee=purch, redemption_fee=redem,
                    fund_size=f["size"],
                    latest_nav=latest.nav if latest else None,
                    latest_nav_date=latest.date if latest else None,
                    source="mock",
                )
        return None

    async def get_nav_history(
        self, fund_code: str, start: date | None = None, end: date | None = None
    ) -> list[NavPoint]:
        if fund_code not in self._nav_cache:
            self._nav_cache[fund_code] = self._generate_nav(fund_code)
        points = self._nav_cache[fund_code]
        if start is None and end is None:
            return list(points)
        return [p for p in points if (start is None or p.date >= start) and (end is None or p.date <= end)]

    def _generate_nav(self, fund_code: str) -> list[NavPoint]:
        meta = next((f for f in MOCK_FUNDS if f["code"] == fund_code), None)
        if meta is None:
            return []
        rng = _rng_for(f"nav-{fund_code}")
        days = _business_days(date.today() - timedelta(days=int(self._years * 365)), self._end_date)
        n = len(days)
        rets = rng.normal(meta["drift"], meta["vol"], n)
        # 注入若干趋势段与回撤段，让图形更接近真实
        i = 0
        while i < n:
            seg = int(rng.integers(40, 110))
            if rng.random() < 0.38:
                sign = 1.0 if rng.random() < 0.55 else -1.0
                rets[i : i + seg] += sign * rng.uniform(0.0006, 0.0018)
            i += seg
        nav = meta["start_nav"] * np.exp(np.cumsum(rets))
        daily_returns = np.diff(nav, prepend=nav[0]) / np.where(nav[0] != 0, nav[0], 1.0)
        # 债券型 daily_return 太大时收缩到合理范围
        points: list[NavPoint] = []
        for d, price, ret in zip(days, nav, daily_returns):
            points.append(
                NavPoint(
                    date=d,
                    nav=float(round(price, 4)),
                    accumulated_nav=float(round(price * rng.uniform(1.1, 1.6), 4)),
                    daily_return=float(round(ret, 6)),
                    volume=float(int(rng.uniform(0.8e6, 8e6))),
                    source="mock",
                )
            )
        return points

    async def get_estimate(self, fund_code: str) -> Estimate | None:
        """交易时段内返回模拟盘中估值（明确标记为估值）。"""
        now = datetime.now(_TZ_CN)
        trading = now.weekday() < 5 and time(9, 30) <= now.time() <= time(15, 0)
        if not trading:
            return None
        navs = await self.get_nav_history(fund_code)
        if not navs:
            return None
        rng = _rng_for(f"est-{fund_code}-{now.strftime('%Y%m%d')}")
        last = navs[-1]
        drift = rng.uniform(-0.006, 0.006)
        return Estimate(
            fund_code=fund_code,
            nav=float(round(last.nav * (1 + drift), 4)),
            return_pct=float(round(drift * 100, 2)),
            time=now,
            source="mock-estimate",
        )

    async def get_holdings(self, fund_code: str, report_date: date | None = None) -> list[HoldingItem]:
        rows = MOCK_HOLDINGS.get(fund_code, [])
        report = report_date or (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
        items: list[HoldingItem] = []
        for code, name, weight, industry in rows:
            meta = next((f for f in MOCK_FUNDS if f["code"] == fund_code), None)
            mv = round(weight / 100 * (meta["size"] if meta else 50), 2)
            items.append(
                HoldingItem(
                    report_date=report, stock_code=code, stock_name=name,
                    weight=weight, industry=industry, market_value=mv, source="mock",
                )
            )
        return items

    # ------------------------------------------------------------ 指数

    async def get_index_snapshot(self, index_code: str) -> IndexSnapshot | None:
        meta = next((i for i in MOCK_INDEXES if i["code"] == index_code), None)
        if meta is None:
            return None
        bars = await self.get_index_history(index_code)
        if not bars:
            return None
        last = bars[-1]
        prev = bars[-2].close if len(bars) > 1 else last.open
        change = round(last.close - prev, 2)
        change_pct = round(change / prev * 100, 2) if prev else 0.0
        return IndexSnapshot(
            index_code=index_code, index_name=meta["name"], market=meta["market"],
            latest_close=last.close, change=change, change_pct=change_pct,
            data_time=datetime.combine(last.date, time(15, 0), tzinfo=_TZ_CN), source="mock",
        )

    async def get_index_history(
        self, index_code: str, start: date | None = None, end: date | None = None
    ) -> list[IndexBar]:
        if index_code not in self._index_cache:
            self._index_cache[index_code] = self._generate_index(index_code)
        bars = self._index_cache[index_code]
        if start is None and end is None:
            return list(bars)
        return [b for b in bars if (start is None or b.date >= start) and (end is None or b.date <= end)]

    def _generate_index(self, index_code: str) -> list[IndexBar]:
        meta = next((i for i in MOCK_INDEXES if i["code"] == index_code), None)
        if meta is None:
            return []
        rng = _rng_for(f"idx-{index_code}")
        days = _business_days(date.today() - timedelta(days=int(self._years * 365)), self._end_date)
        rets = rng.normal(meta["drift"], meta["vol"], len(days))
        close = meta["base"] * np.exp(np.cumsum(rets))
        bars: list[IndexBar] = []
        for d, c in zip(days, close):
            o = c * (1 + rng.normal(0, meta["vol"] / 3))
            hi = max(o, c) * (1 + abs(rng.normal(0, meta["vol"] / 4)))
            lo = min(o, c) * (1 - abs(rng.normal(0, meta["vol"] / 4)))
            bars.append(
                IndexBar(
                    date=d, open=float(round(o, 2)), high=float(round(hi, 2)),
                    low=float(round(lo, 2)), close=float(round(c, 2)),
                    volume=float(int(rng.uniform(2e8, 6e8))), source="mock",
                )
            )
        return bars

    # ------------------------------------------------------------ 宏观

    async def get_macro(self, indicator: str | None = None, limit: int = 200) -> list[MacroItem]:
        items: list[MacroItem] = []
        for name, base, unit, vol in _MACRO_BASE:
            if indicator and indicator not in name and name not in indicator:
                continue
            rng = _rng_for(f"macro-{name}")
            quarterly = name.startswith("GDP")
            periods = 8 if quarterly else 24
            values = base + np.cumsum(rng.normal(0, vol, periods))
            for k in range(periods):
                if quarterly:
                    q = (date.today().year * 4 + (date.today().month - 1) // 3) - periods + k + 1
                    period = f"{q // 4}Q{q % 4 + 1}"
                    published = date(q // 4, (q % 4) * 3 + 1, 15)
                else:
                    total = date.today().year * 12 + date.today().month - 1 - periods + k + 1
                    period = f"{total // 12}-{total % 12 + 1:02d}"
                    published = date(total // 12, total % 12 + 1, 15)
                prev = float(values[k - 1]) if k > 0 else float(values[k])
                items.append(
                    MacroItem(
                        indicator=name, value=float(round(values[k], 2)), unit=unit,
                        period=period, change=float(round(values[k] - prev, 2)),
                        published_at=published, source="mock",
                    )
                )
        # limit 按每个指标最近 N 期截断（保证所有指标都保留）
        if limit > 0:
            per_indicator: dict[str, list[MacroItem]] = {}
            for item in items:
                per_indicator.setdefault(item.indicator, []).append(item)
            items = [v for group in per_indicator.values() for v in group[-limit:]]
        return items

    # ------------------------------------------------------------ 新闻 / 政策

    async def get_news(self, limit: int = 50) -> list[NewsItem]:
        now = utcnow()
        items: list[NewsItem] = []
        for i, (title, industry, sentiment, importance, content) in enumerate(_MOCK_NEWS):
            published = now - timedelta(hours=i * 3 + 1)
            items.append(
                NewsItem(
                    title=title, content=content, source="演示财经媒体（mock）",
                    url="", published_at=published, related_fund=None,
                    related_industry=industry, sentiment=sentiment, importance=importance,
                )
            )
        return items[:limit]

    async def get_policies(self, limit: int = 50) -> list[PolicyItem]:
        now = utcnow()
        items: list[PolicyItem] = []
        for i, (title, dept, ptype, industry, sentiment, impact, importance, content) in enumerate(
            _MOCK_POLICIES
        ):
            published = now - timedelta(days=i * 4 + 1)
            items.append(
                PolicyItem(
                    title=title, content=content, source="公开政策信息（mock）",
                    url="", published_at=published, department=dept, policy_type=ptype,
                    related_industry=industry, sentiment=sentiment,
                    impact_score=impact, importance=importance,
                )
            )
        return items[:limit]

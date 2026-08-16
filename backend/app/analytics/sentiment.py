"""中文财经情感词典：情绪评分 + 行业识别。"""
from __future__ import annotations

POSITIVE_WORDS = {
    "利好", "上涨", "增长", "超预期", "回升", "改善", "强劲", "回暖", "提振", "创新高",
    "突破", "扩张", "加速", "增持", "回购", "降准", "降息", "宽松", "放量", "景气",
    "复苏", "修复", "走强", "反弹", "净流入", "向好", "繁荣", "红利", "支持", "扶持",
    "获批", "落地", "加码", "延续", "稳定", "改善", "超卖", "筑底", "反转",
}
NEGATIVE_WORDS = {
    "利空", "下跌", "下滑", "不及预期", "回落", "恶化", "承压", "低迷", "衰退", "风险",
    "违约", "亏损", "减持", "抛售", "收缩", "放缓", "走弱", "崩盘", "净流出", "不确定性",
    "收紧", "加息", "通胀", "通缩", "危机", "退市", "处罚", "违规", "爆雷", "警惕",
    "预警", "调查", "下调", "缩量", "失守", "破位",
}
NEGATION_WORDS = {"不", "无", "没有", "未", "别", "难以", "避免", "抑制"}

INDUSTRY_KEYWORDS: dict[str, set[str]] = {
    "新能源": {"新能源", "光伏", "锂电", "储能", "风电", "电动车", "充电桩", "宁德时代", "电池"},
    "半导体": {"半导体", "芯片", "集成电路", "晶圆", "光刻", "国产替代", "存储"},
    "医药生物": {"医药", "创新药", "医疗器械", "疫苗", "集采", "生物医药", "医院", "药企"},
    "食品饮料": {"白酒", "消费", "食品", "饮料", "乳业", "啤酒", "茅台"},
    "金融": {"银行", "券商", "保险", "金融", "利率", "央行", "信贷", "流动性", "降准", "降息"},
    "房地产": {"房地产", "地产", "楼市", "二手房", "住房", "按揭"},
    "人工智能": {"人工智能", "AI", "大模型", "算力", "数据要素", "机器人", "智能"},
    "互联网": {"互联网", "平台经济", "电商", "游戏", "直播", "社交"},
    "汽车": {"汽车", "车企", "整车", "乘用车", "购置税"},
    "军工": {"军工", "国防", "航天", "航空"},
    "能源": {"原油", "石油", "煤炭", "天然气", "油价"},
    "债券": {"债券", "国债", "收益率", "债市", "信用债"},
    "消费": {"消费", "零售", "社零", "以旧换新", "家电"},
    "海外": {"美联储", "美股", "纳斯达克", "标普", "美元", "加息", "降息"},
}


def score_text(text: str) -> float:
    """基于词典的情绪评分，返回 -1..1。"""
    if not text:
        return 0.0
    pos = 0
    neg = 0
    for word in POSITIVE_WORDS:
        if word in text:
            pos += 1
    for word in NEGATIVE_WORDS:
        if word in text:
            neg += 1
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 4)


def sentiment_label(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


def detect_industries(text: str) -> list[str]:
    """从文本识别涉及的行业。"""
    if not text:
        return []
    found: list[str] = []
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(industry)
    return found


def importance_score(text: str, title: str = "") -> float:
    """简单重要性启发式：政策/央行/重磅词 + 篇幅。"""
    base = 0.4
    strong = {"央行", "国务院", "证监会", "财政部", "发改委", "降准", "降息", "重磅", "出台", "发布", "新政"}
    combined = f"{title} {text}"
    hits = sum(1 for w in strong if w in combined)
    base += min(hits * 0.12, 0.4)
    base += min(len(combined) / 2000 * 0.2, 0.2)
    return round(min(base, 1.0), 4)

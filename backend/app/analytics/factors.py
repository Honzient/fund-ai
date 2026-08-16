"""多因子评分引擎（核心量化逻辑）。

7 个维度：趋势 / 波动 / 风险 / 基金质量 / 宏观 / 行业 / 市场情绪。
每个结论都带 evidence（可追溯到原始数据），绝不输出无依据的判断。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.indicators import latest_indicators
from app.utils.dates import today

FACTOR_WEIGHTS: dict[str, float] = {
    "trend": 0.25,
    "volatility": 0.10,
    "risk": 0.15,
    "quality": 0.10,
    "macro": 0.10,
    "industry": 0.15,
    "sentiment": 0.15,
}

DIMENSION_NAMES = {
    "trend": "趋势",
    "volatility": "波动率",
    "risk": "风险",
    "quality": "基金质量",
    "macro": "宏观",
    "industry": "行业",
    "sentiment": "市场情绪",
}


@dataclass
class FactorContext:
    df: pd.DataFrame  # 净值历史（含日期升序）
    risk_metrics: dict = field(default_factory=dict)
    fund_age_years: float = 0.0
    fund_size: float | None = None  # 亿元
    holdings_industries: dict[str, float] = field(default_factory=dict)  # 行业 -> 权重%
    top10_weight: float = 0.0  # Top10 持仓集中度 %
    macro_latest: dict[str, float] = field(default_factory=dict)  # 指标名 -> 最新值
    news_avg_sentiment: float = 0.0
    news_industry_sentiment: dict[str, float] = field(default_factory=dict)
    policy_avg_impact: float = 0.0
    policy_industry_impact: dict[str, float] = field(default_factory=dict)
    market_20d_return: float = 0.0  # 小数
    market_60d_return: float = 0.0
    market_rsi: float | None = None


@dataclass
class FactorResult:
    dimension: str
    name: str
    score: float  # 0-100
    direction: str  # 偏多 / 中性 / 偏空
    detail: str
    evidence: dict


def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pct_rank(series: pd.Series) -> float:
    """最新值在自身历史中的分位（0..1）。"""
    if len(series) < 5:
        return 0.5
    return float((series < series.iloc[-1]).mean())


def _direction(score: float) -> str:
    if score >= 60:
        return "偏多"
    if score <= 40:
        return "偏空"
    return "中性"


# ---------------------------------------------------------------- 趋势因子


def trend_factor(ctx: FactorContext) -> FactorResult:
    ind = latest_indicators(ctx.df)
    if not ind:
        return FactorResult("trend", "趋势", 50.0, "中性", "数据不足", {})
    score = 50.0
    evidence: dict[str, Any] = {}
    notes: list[str] = []

    def _cmp(cond: bool, weight: float, note: str):
        nonlocal score
        score += weight if cond else -weight
        if cond:
            notes.append(note)

    if ind.get("ma20") and ind.get("ma60"):
        last_price = float(ctx.df["nav"].iloc[-1])
        _cmp(last_price > ind["ma20"], 9, "价格位于MA20上方")
        _cmp(last_price > ind["ma60"], 8, "价格位于MA60上方")
        _cmp(ind["ma20"] > ind["ma60"], 7, "MA20上穿MA60，均线多头排列")
        evidence.update({"price": last_price, "ma20": ind["ma20"], "ma60": ind["ma60"]})
    if ind.get("macd_hist") is not None:
        _cmp(ind["macd_hist"] > 0, 5, "MACD柱为正，动能向上")
        evidence["macd_hist"] = ind["macd_hist"]
    rsi_v = ind.get("rsi14")
    if rsi_v is not None:
        if 50 <= rsi_v <= 70:
            score += 5
            notes.append("RSI处于健康强势区间")
        elif rsi_v < 30:
            score += 3
            notes.append("RSI超卖，存在反弹空间")
        elif rsi_v > 80:
            score -= 6
            notes.append("RSI超买，短期回调风险")
        evidence["rsi14"] = rsi_v
    if ind.get("momentum_20d") is not None:
        mom_series = ctx.df["nav"].pct_change(20).dropna()
        if len(mom_series) >= 5:
            rank = float((mom_series < mom_series.iloc[-1]).mean())
            score += (rank - 0.5) * 24
            notes.append(f"20日动量 {ind['momentum_20d'] * 100:.2f}%，处历史 {rank * 100:.0f}% 分位")
            evidence["momentum_20d"] = ind["momentum_20d"]
    if ind.get("momentum_60d") is not None:
        mom_series = ctx.df["nav"].pct_change(60).dropna()
        if len(mom_series) >= 5:
            rank = float((mom_series < mom_series.iloc[-1]).mean())
            score += (rank - 0.5) * 20
            evidence["momentum_60d"] = ind["momentum_60d"]
    score = _clip(score)
    detail = "；".join(notes) if notes else "趋势信号中性"
    return FactorResult("trend", "趋势", round(score, 1), _direction(score), detail, evidence)


# ---------------------------------------------------------------- 波动率因子


def volatility_factor(ctx: FactorContext) -> FactorResult:
    ind = latest_indicators(ctx.df)
    vol = ind.get("vol_20")
    if vol is None:
        return FactorResult("volatility", "波动率", 50.0, "中性", "数据不足", {})
    vol_series = ctx.df["nav"].pct_change().rolling(20, min_periods=20).std(ddof=0).dropna()
    rank = float((vol_series < vol_series.iloc[-1]).mean()) if len(vol_series) >= 5 else 0.5
    score = 50 + (0.5 - rank) * 100  # 波动率处于历史低分位 → 高分
    score = _clip(score)
    if rank < 0.25:
        detail = f"20日年化波动率 {vol * 100:.1f}% 处历史低位，价格平稳"
    elif rank > 0.75:
        detail = f"20日年化波动率 {vol * 100:.1f}% 处历史高位，波动加剧"
    else:
        detail = f"20日年化波动率 {vol * 100:.1f}%，处历史中位"
    return FactorResult(
        "volatility", "波动率", round(score, 1), _direction(score), detail,
        {"vol_20": vol, "vol_20_pct_rank": round(rank, 3)},
    )


# ---------------------------------------------------------------- 风险因子


def risk_factor(ctx: FactorContext) -> FactorResult:
    m = ctx.risk_metrics
    if not m:
        return FactorResult("risk", "风险", 50.0, "中性", "数据不足", {})
    score = 50.0
    notes: list[str] = []
    mdd = m.get("max_drawdown")  # 负值百分比
    if mdd is not None:
        if mdd > -10:
            score += 15
            notes.append(f"最大回撤 {mdd:.1f}%，回撤控制良好")
        elif mdd > -20:
            score += 0
            notes.append(f"最大回撤 {mdd:.1f}%，处于中等水平")
        else:
            score -= 15
            notes.append(f"最大回撤 {mdd:.1f}%，历史回撤较深")
    sharpe = m.get("sharpe")
    if sharpe is not None:
        if sharpe > 1:
            score += 12
            notes.append(f"夏普比率 {sharpe:.2f}，风险调整后收益优秀")
        elif sharpe > 0.3:
            score += 4
            notes.append(f"夏普比率 {sharpe:.2f}，尚可")
        elif sharpe <= 0:
            score -= 10
            notes.append(f"夏普比率 {sharpe:.2f}，风险调整后收益为负")
    sortino = m.get("sortino")
    if sortino is not None and sortino < 0:
        score -= 6
        notes.append("Sortino 为负，下行波动未获补偿")
    cvar = m.get("cvar_95")
    if cvar is not None:
        if cvar > 3:
            score -= 6
            notes.append(f"95% CVaR {cvar:.2f}%，尾部损失较大")
        else:
            score += 4
            notes.append(f"95% CVaR {cvar:.2f}%，尾部风险可控")
    score = _clip(score)
    return FactorResult(
        "risk", "风险", round(score, 1), _direction(score), "；".join(notes) or "风险指标中性",
        {"max_drawdown": mdd, "sharpe": sharpe, "sortino": sortino, "cvar_95": cvar},
    )


# ---------------------------------------------------------------- 质量因子


def quality_factor(ctx: FactorContext) -> FactorResult:
    score = 50.0
    notes: list[str] = []
    if ctx.fund_age_years >= 8:
        score += 12
        notes.append(f"成立 {ctx.fund_age_years:.1f} 年，经历多轮牛熊")
    elif ctx.fund_age_years >= 3:
        score += 5
        notes.append(f"成立 {ctx.fund_age_years:.1f} 年，运作时间中等")
    else:
        score -= 5
        notes.append("成立时间较短，历史参考有限")
    if ctx.fund_size:
        if 10 <= ctx.fund_size <= 500:
            score += 10
            notes.append(f"规模 {ctx.fund_size:.1f} 亿元，处于舒适区间")
        elif ctx.fund_size > 800:
            score -= 3
            notes.append(f"规模 {ctx.fund_size:.1f} 亿元，调仓灵活性可能下降")
        else:
            score -= 5
            notes.append(f"规模 {ctx.fund_size:.1f} 亿元，存在清盘与流动性风险")
    if ctx.top10_weight:
        if 30 <= ctx.top10_weight <= 60:
            score += 10
            notes.append(f"Top10 集中度 {ctx.top10_weight:.1f}%，攻守平衡")
        elif ctx.top10_weight > 75:
            score -= 10
            notes.append(f"Top10 集中度 {ctx.top10_weight:.1f}%，个股风险集中")
        else:
            score += 4
            notes.append(f"Top10 集中度 {ctx.top10_weight:.1f}%，持仓分散")
    weights = list(ctx.holdings_industries.values())
    if weights:
        hhi = sum((w / 100) ** 2 for w in weights)
        if hhi > 0.5:
            score -= 10
            notes.append(f"行业集中度(HHI={hhi:.2f})偏高，行业风险暴露集中")
        elif hhi < 0.25:
            score += 6
            notes.append(f"行业分散(HHI={hhi:.2f})，单一行业冲击有限")
    score = _clip(score)
    return FactorResult(
        "quality", "基金质量", round(score, 1), _direction(score),
        "；".join(notes) or "质量因子中性",
        {"fund_age_years": round(ctx.fund_age_years, 2), "fund_size": ctx.fund_size,
         "top10_weight": ctx.top10_weight, "industries": ctx.holdings_industries},
    )


# ---------------------------------------------------------------- 宏观因子


def macro_factor(ctx: FactorContext) -> FactorResult:
    macro = ctx.macro_latest
    if not macro:
        return FactorResult("macro", "宏观", 50.0, "中性", "宏观数据不足，中性处理", {})
    score = 50.0
    notes: list[str] = []
    pmi = macro.get("制造业PMI")
    if pmi is not None:
        if pmi > 50.2:
            score += 15
            notes.append(f"PMI {pmi} 处于扩张区间")
        elif pmi < 49.5:
            score -= 15
            notes.append(f"PMI {pmi} 低于荣枯线，经济动能偏弱")
        else:
            score += 3
            notes.append(f"PMI {pmi} 位于荣枯线附近")
    cpi = macro.get("CPI同比")
    if cpi is not None:
        if 0 < cpi <= 3:
            score += 8
            notes.append(f"CPI {cpi}% 温和，通胀压力可控")
        elif cpi > 4:
            score -= 8
            notes.append(f"CPI {cpi}% 偏高，通胀约束政策空间")
    m2 = macro.get("M2同比")
    if m2 is not None:
        if 7 <= m2 <= 10:
            score += 6
            notes.append(f"M2 同比 {m2}%，流动性合理充裕")
        elif m2 > 11:
            score -= 3
            notes.append(f"M2 同比 {m2}%，流动性宽松但需防通胀")
    lpr = macro.get("1年期LPR")
    if lpr is not None and lpr <= 3.3:
        score += 5
        notes.append(f"1年期LPR {lpr}%，利率处于低位，利好权益估值")
    fx = macro.get("美元兑人民币")
    if fx is not None:
        if 7.3 <= fx <= 7.4:
            score -= 4
            notes.append(f"人民币汇率 {fx}，贬值压力需关注")
        else:
            score += 4
            notes.append(f"人民币汇率 {fx}，总体稳定")
    score = _clip(score)
    return FactorResult(
        "macro", "宏观", round(score, 1), _direction(score), "；".join(notes) or "宏观中性",
        dict(macro),
    )


# ---------------------------------------------------------------- 行业因子


def industry_factor(ctx: FactorContext) -> FactorResult:
    industries = ctx.holdings_industries
    if not industries:
        return FactorResult("industry", "行业", 50.0, "中性", "无持仓行业数据，中性处理", {})
    total_weight = sum(industries.values())
    weighted = 0.0
    notes: list[str] = []
    top = sorted(industries.items(), key=lambda kv: kv[1], reverse=True)[:3]
    for industry, weight in top:
        w = weight / total_weight
        news_s = ctx.news_industry_sentiment.get(industry, 0.0)
        policy_s = ctx.policy_industry_impact.get(industry, 0.0)
        sub = 50 + news_s * 45 + policy_s * 40
        weighted += sub * w
        if sub > 58:
            notes.append(f"{industry}（权重{weight:.0f}%）：新闻/政策情绪偏正面")
        elif sub < 42:
            notes.append(f"{industry}（权重{weight:.0f}%）：新闻/政策情绪偏负面")
    # 加上市场贝塔代理：市场20日动量
    weighted = weighted * 0.75 + (50 + ctx.market_20d_return * 400) * 0.25
    score = _clip(weighted)
    return FactorResult(
        "industry", "行业", round(score, 1), _direction(score),
        "；".join(notes) if notes else "持仓行业信号中性",
        {"industries": industries, "news_industry_sentiment": ctx.news_industry_sentiment,
         "policy_industry_impact": ctx.policy_industry_impact},
    )


# ---------------------------------------------------------------- 市场情绪因子


def sentiment_factor(ctx: FactorContext) -> FactorResult:
    score = 50.0
    notes: list[str] = []
    score += ctx.news_avg_sentiment * 40
    notes.append(f"新闻情绪均值 {ctx.news_avg_sentiment:.2f}")
    score += ctx.policy_avg_impact * 35
    notes.append(f"政策影响均值 {ctx.policy_avg_impact:.2f}")
    if ctx.market_20d_return > 0.01:
        score += 8
        notes.append(f"市场20日收益 {ctx.market_20d_return * 100:.1f}%，风险偏好回升")
    elif ctx.market_20d_return < -0.01:
        score -= 8
        notes.append(f"市场20日收益 {ctx.market_20d_return * 100:.1f}%，风险偏好回落")
    if ctx.market_rsi is not None:
        if ctx.market_rsi > 75:
            score -= 5
            notes.append("市场指数RSI偏高，短期情绪过热")
        elif ctx.market_rsi < 30:
            score += 4
            notes.append("市场指数RSI超卖，情绪修复概率上升")
    score = _clip(score)
    return FactorResult(
        "sentiment", "市场情绪", round(score, 1), _direction(score),
        "；".join(notes) or "情绪中性",
        {"news_avg_sentiment": ctx.news_avg_sentiment, "policy_avg_impact": ctx.policy_avg_impact,
         "market_20d_return": ctx.market_20d_return, "market_rsi": ctx.market_rsi},
    )


FACTOR_FUNCS = {
    "trend": trend_factor,
    "volatility": volatility_factor,
    "risk": risk_factor,
    "quality": quality_factor,
    "macro": macro_factor,
    "industry": industry_factor,
    "sentiment": sentiment_factor,
}


def regime_labels(ctx: FactorContext) -> dict[str, str]:
    """短/中/长期趋势判断（基于动量与均线）。"""
    ind = latest_indicators(ctx.df)

    def _label(value: float | None, up: float, down: float) -> str:
        if value is None:
            return "中性"
        if value > up:
            return "偏多"
        if value < down:
            return "偏空"
        return "中性"

    mom20 = ind.get("momentum_20d")
    mom60 = ind.get("momentum_60d")
    mom250 = ind.get("momentum_250d")
    short = _label(mom20, 0.005, -0.005)
    if short == "中性" and ind.get("macd_hist") is not None:
        short = "偏多" if ind["macd_hist"] > 0 else "偏空"
    return {
        "short": short,
        "medium": _label(mom60, 0.02, -0.02),
        "long": _label(mom250, 0.06, -0.06),
    }


def build_main_risks(ctx: FactorContext, factors: dict[str, FactorResult]) -> list[dict]:
    """汇总主要风险（宏观/政策/市场/行业/基金自身）。"""
    risks: list[dict] = []

    def add(category: str, detail: str, severity: str, evidence: dict | None = None):
        risks.append({"category": category, "detail": detail, "severity": severity, "evidence": evidence or {}})

    macro = ctx.macro_latest
    pmi = macro.get("制造业PMI")
    if pmi is not None and pmi < 49.5:
        add("宏观风险", f"制造业PMI {pmi} 处于收缩区间，经济增长动能偏弱", "medium", {"PMI": pmi})
    cpi = macro.get("CPI同比")
    if cpi is not None and cpi > 3.5:
        add("宏观风险", f"CPI 同比 {cpi}% 偏高，通胀可能约束政策空间", "medium", {"CPI": cpi})

    if ctx.policy_avg_impact < -0.2:
        add("政策风险", "近期相关政策总体偏负面，行业政策存在不确定性", "medium", {})

    if ctx.market_20d_return < -0.02:
        add("市场风险", f"市场20日收益 {ctx.market_20d_return * 100:.1f}%，短期风险偏好回落", "medium", {})
    if ctx.market_rsi is not None and ctx.market_rsi > 78:
        add("市场风险", "市场指数RSI处于高位，短期存在情绪过热后的回撤风险", "low", {})

    mdd = ctx.risk_metrics.get("max_drawdown")
    if mdd is not None and mdd < -20:
        add("基金自身风险", f"历史最大回撤 {mdd:.1f}%，回撤较深，需评估自身风险承受能力", "high", {"max_drawdown": mdd})
    vol20 = latest_indicators(ctx.df).get("vol_20")
    if vol20 is not None:
        vol_series = ctx.df["nav"].pct_change().rolling(20, min_periods=20).std(ddof=0).dropna()
        if len(vol_series) >= 5:
            rank = float((vol_series < vol_series.iloc[-1]).mean())
            if rank > 0.8:
                add("基金自身风险", "20日波动率处于历史高位，净值波动加大", "medium", {"vol_20": vol20})

    if ctx.top10_weight > 75:
        add("基金自身风险", f"Top10 持仓集中度 {ctx.top10_weight:.1f}%，个股风险集中", "medium", {})

    if not risks:
        add("综合", "未发现显著单项风险，但任何投资均有本金损失可能", "low", {})
    return risks[:5]


def compute_factor_scores(ctx: FactorContext) -> dict:
    """计算全部因子得分并汇总，输出可解释的分析结果。"""
    factors: dict[str, FactorResult] = {}
    for key, func in FACTOR_FUNCS.items():
        try:
            factors[key] = func(ctx)
        except Exception:  # noqa: BLE001 单因子异常不能中断整体评分
            factors[key] = FactorResult(key, DIMENSION_NAMES.get(key, key), 50.0, "中性", "因子计算异常，中性处理", {})

    score_breakdown = {k: v.score for k, v in factors.items()}
    composite = sum(FACTOR_WEIGHTS[k] * factors[k].score for k in FACTOR_WEIGHTS)
    composite = round(_clip(composite), 1)

    positive = [
        {
            "factor": v.name,
            "reason": v.detail,
            "evidence": v.evidence,
            "value": v.score,
        }
        for v in factors.values()
        if v.score >= 60
    ]
    negative = [
        {
            "factor": v.name,
            "reason": v.detail,
            "evidence": v.evidence,
            "value": v.score,
        }
        for v in factors.values()
        if v.score <= 40
    ]
    positive.sort(key=lambda x: -x["value"])
    negative.sort(key=lambda x: x["value"])

    regime = regime_labels(ctx)
    return {
        "score": composite,
        "score_breakdown": score_breakdown,
        "trend": regime,
        "positive_factors": positive[:5],
        "negative_factors": negative[:5],
        "main_risks": build_main_risks(ctx, factors),
        "computed_at": today().isoformat(),
    }

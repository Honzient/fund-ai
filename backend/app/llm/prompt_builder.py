"""PromptBuilder：把 Context 编译为 LLM 消息（System 规范 + 注入数据）。"""
from __future__ import annotations

import json

SYSTEM_RULES = """你是一个基金投资研究与辅助分析助手，回答必须严谨、可追溯、不夸大。

【必须遵守的规则】
1. 所有数据仅来自下方「数据上下文」，明确标注数据时间（数据截至 {data_as_of}）。
2. 明确区分事实（数据所示）与推断（你的判断）。
3. 给出分析依据；主要结论尽量能追溯到上下文中的数据。
4. 必须给出主要风险，并做情景分析：乐观情景 / 基准情景 / 悲观情景。
5. 数据不足时明确说"数据不足"，不得脑补。
6. 严禁编造不存在的数据、新闻、政策或行情；未提供的信息一律不得捏造。
7. 严禁声称能够准确预测市场涨跌，严禁承诺收益。所有预测只能表达为概率、评分、置信度与情景。
8. 涉及基金/股票名称与代码必须与上下文一致。
9. 回答使用中文，结构化输出（标题/列表），末尾可附简短免责声明。
10. 你的输出仅用于投资研究参考，不构成投资建议。"""


def _compact_number(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_system_prompt(context: dict) -> str:
    """System 消息：行为规范 + 压缩后的数据上下文。"""
    data_as_of = context.get("data_as_of") or "未知"
    parts = [SYSTEM_RULES.format(data_as_of=data_as_of), "", "【数据上下文】"]

    # 市场
    market = context.get("market") or {}
    regime = market.get("market_regime") or {}
    parts.append(
        f"市场环境：{regime.get('label', '未知')}（评分 {regime.get('score', '—')}）；"
        f"驱动因素：{'、'.join(regime.get('drivers', [])) or '无'}"
    )

    # 宏观
    macro = context.get("macro") or []
    if macro:
        parts.append(
            "宏观数据：" + "；".join(
                f"{m['indicator']}={_compact_number(m['value'])}{m.get('unit') or ''}({m.get('period') or ''})"
                for m in macro[:12]
            )
        )

    # 每只基金
    for fund in context.get("funds", []):
        if "error" in fund:
            parts.append(f"基金 {fund.get('fund_code')}：{fund['error']}")
            continue
        profile = fund.get("fund_profile") or {}
        perf = fund.get("performance") or {}
        ind = fund.get("technical_indicators") or {}
        risk = fund.get("risk_metrics") or {}
        pred = fund.get("prediction") or {}
        parts.append(
            f"\n## 基金：{profile.get('fund_name')}（{profile.get('fund_code')}）\n"
            f"- 类型：{profile.get('fund_type') or '—'}；公司：{profile.get('company') or '—'}；"
            f"基金经理：{profile.get('manager') or '—'}\n"
            f"- 最新净值：{_compact_number(profile.get('latest_nav'))}（{profile.get('latest_nav_date') or '—'}）\n"
            f"- 近期表现：1日 {_compact_number(perf.get('return_1d'), 2)}% / "
            f"5日 {_compact_number(perf.get('return_5d'), 2)}% / "
            f"20日 {_compact_number(perf.get('return_20d'), 2)}% / "
            f"60日 {_compact_number(perf.get('return_60d'), 2)}% / "
            f"1年 {_compact_number(perf.get('return_1y'), 2)}% / "
            f"年初至今 {_compact_number(perf.get('return_ytd'), 2)}%\n"
            f"- AI综合评分：{fund.get('score', '—')}/100；趋势：短期 {fund.get('trend', {}).get('short', '—')} / "
            f"中期 {fund.get('trend', {}).get('medium', '—')} / 长期 {fund.get('trend', {}).get('long', '—')}\n"
            f"- 技术指标：RSI14={_compact_number(ind.get('rsi14'), 2)}，"
            f"MACD柱={_compact_number(ind.get('macd_hist'))}，"
            f"MA20={_compact_number(ind.get('ma20'))}，MA60={_compact_number(ind.get('ma60'))}\n"
            f"- 风险指标：最大回撤 {_compact_number(risk.get('max_drawdown'), 2)}%，"
            f"年化波动率 {_compact_number(risk.get('annual_volatility'), 2)}%，"
            f"Sharpe {_compact_number(risk.get('sharpe'), 3)}，Sortino {_compact_number(risk.get('sortino'), 3)}"
            + (f"，Beta {_compact_number(risk.get('beta'), 3)}，Alpha {_compact_number(risk.get('alpha'), 2)}%" if risk.get("beta") is not None else "")
            + "\n"
        )
        for horizon, p in pred.items():
            probs = p.get("probabilities") or {}
            parts.append(
                f"- 模型预测（{horizon}，{p.get('horizon_days', '—')}日，模型 {p.get('model_version', '—')}，置信度 {p.get('confidence', '—')}）："
                f"上涨 {probs.get('up', '—')}% / 震荡 {probs.get('range', '—')}% / 下跌 {probs.get('down', '—')}%"
            )
        positives = fund.get("positive_factors") or []
        negatives = fund.get("negative_factors") or []
        if positives:
            parts.append("- 正面因素：" + "；".join(p["reason"] for p in positives[:3]))
        if negatives:
            parts.append("- 负面因素：" + "；".join(n["reason"] for n in negatives[:3]))
        risks = fund.get("main_risks") or []
        if risks:
            parts.append("- 主要风险：" + "；".join(f"[{r['category']}]{r['detail']}" for r in risks))
        holdings = fund.get("holdings") or {}
        top10 = holdings.get("top10") or []
        if top10:
            parts.append(
                "- 前5持仓：" + "、".join(f"{h['stock_name']}({h['weight']}%)" for h in top10)
            )
        industries = holdings.get("industry_distribution") or []
        if industries:
            parts.append(
                "- 行业暴露：" + "、".join(f"{i['industry']} {i['weight']}%" for i in industries[:5])
            )
        for news in fund.get("news", [])[:3]:
            parts.append(
                f"- 相关新闻[{news.get('published_at', '')[:10]}]（{news.get('sentiment_label', '')}，"
                f"来源：{news.get('source', '')}）：{news.get('title', '')}"
            )
        for policy in fund.get("policies", [])[:3]:
            parts.append(
                f"- 相关政策[{policy.get('published_at', '')[:10]}]（{policy.get('department', '')}）："
                f"{policy.get('title', '')}"
            )

    # 市场级新闻/政策
    news = context.get("news") or []
    if news:
        parts.append("\n重要新闻：" + "；".join(f"[{n.get('published_at', '')[:10]}] {n.get('title', '')}" for n in news[:5]))
    policies = context.get("policies") or []
    if policies:
        parts.append("重要政策：" + "；".join(f"[{p.get('published_at', '')[:10]}] {p.get('title', '')}" for p in policies[:5]))

    parts.append("\n【回答要求】基于以上数据回答用户问题。数据不足处明确说明，不要编造补充。")
    return "\n".join(parts)


def build_messages(
    context: dict,
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """组装完整消息序列：System(规范+Context) + 历史 + 用户消息。"""
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(context)}]
    for item in history[-12:]:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def context_digest(context: dict) -> str:
    """用于日志的轻量摘要（不含敏感信息）。"""
    return json.dumps(
        {
            "funds": [f.get("fund_profile", {}).get("fund_code") for f in context.get("funds", [])],
            "data_as_of": context.get("data_as_of"),
        },
        ensure_ascii=False,
    )

"""报告服务：每日基金报告（Markdown / HTML）。"""
from __future__ import annotations

import markdown as md_lib

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.llm import LLMUnavailableError, build_messages, get_llm_manager
from app.models import Report
from app.services import analysis_service, market_service, news_service
from app.utils.asyncs import run_async
from app.utils.dates import now_local

log = get_logger("app.task")


def build_daily_report(
    db,
    user_id: int,
    fund_codes: list[str] | None = None,
    trigger: str = "manual",
    llm_summary: bool = True,
) -> Report:
    """生成每日基金报告并落库。"""
    now = now_local()
    title = f"每日基金报告 {now.strftime('%Y-%m-%d %H:%M')}"
    lines = [
        f"# {title}",
        "",
        f"生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 市场概况",
        "",
    ]
    market = market_service.market_overview(db)
    regime = market["market_regime"]
    lines.append(f"- 市场状态：**{regime['label']}**（评分 {regime['score']}）")
    lines.append("- 驱动因素：" + "；".join(regime["drivers"]))
    lines.append("")
    lines.append("| 指数 | 最新 | 涨跌幅 |")
    lines.append("| --- | ---: | ---: |")
    for idx in market["indices"]:
        lines.append(
            f"| {idx['index_name']} | {idx['latest_close'] or '—'} | {idx['change_pct'] if idx['change_pct'] is not None else '—'}% |"
        )
    lines.append("")

    analyses = []
    for code in fund_codes or []:
        try:
            analysis = analysis_service.analyze_fund(db, code, "3M", with_prediction=True)
            analyses.append(analysis)
        except Exception as exc:  # noqa: BLE001
            log.warning("报告生成-基金分析失败 %s: %s", code, exc)
            lines.append(f"## {code}\n\n分析失败：{exc}\n")
            continue

    lines.append("## 基金分析")
    lines.append("")
    for a in analyses:
        fund = a["fund"]
        pred = (a.get("predictions") or {}).get("short") or {}
        probs = pred.get("probabilities") or {}
        lines.append(f"### {fund['fund_name']}（{fund['fund_code']}）")
        lines.append(f"- 趋势：短期 **{a['trend']['short']}** / 中期 **{a['trend']['medium']}** / 长期 **{a['trend']['long']}**")
        lines.append(f"- 风险：最大回撤 {a['risk'].get('max_drawdown', '—')}%，波动率 {a['risk'].get('annual_volatility', '—')}%，Sharpe {a['risk'].get('sharpe', '—')}")
        if probs:
            lines.append(
                f"- 预测（5日）：上涨 {probs.get('up', '—')}% / 震荡 {probs.get('range', '—')}% / 下跌 {probs.get('down', '—')}%"
                f"（置信度 {pred.get('confidence', '—')}，模型 {pred.get('model_version', '—')}）"
            )
        positives = a.get("positive_factors") or []
        negatives = a.get("negative_factors") or []
        if positives:
            lines.append("- 正面因素：" + "；".join(p["reason"] for p in positives[:3]))
        if negatives:
            lines.append("- 负面因素：" + "；".join(n["reason"] for n in negatives[:3]))
        lines.append("")

    # 今日关注 / 风险 / 政策 / 情绪
    lines.append("## 今日关注")
    lines.append("")
    top_news = news_service.news_list(db, limit=3)
    if top_news:
        for n in top_news:
            lines.append(f"- [{n['sentiment_label']}] {n['title']}（{n['source']}）")
    else:
        lines.append("- 暂无重要新闻")
    lines.append("")

    lines.append("## 主要风险")
    lines.append("")
    risk_lines: list[str] = []
    for a in analyses:
        for r in (a.get("main_risks") or [])[:2]:
            risk_lines.append(f"- [{r['category']}] {a['fund']['fund_name']}：{r['detail']}")
    lines.extend(risk_lines[:8] if risk_lines else ["- 未发现显著单项风险"])

    lines.append("")
    lines.append("## 政策影响")
    lines.append("")
    top_policies = news_service.policy_list(db, limit=5)
    if top_policies:
        for p in top_policies:
            lines.append(f"- {p['title']}（{p.get('department') or '公开信息'}）")
    else:
        lines.append("- 暂无重要政策")
    lines.append("")

    lines.append("## 市场情绪")
    lines.append("")
    agg = news_service.aggregate_sentiment(db)
    lines.append(
        f"- 新闻情绪均值：{agg['news']['avg_sentiment']:.2f}（样本 {agg['news']['count']} 条）"
    )
    lines.append(
        f"- 政策情绪均值：{agg['policies']['avg_sentiment']:.2f}（样本 {agg['policies']['count']} 条）"
    )
    lines.append("")

    if llm_summary:
        lines.append("## AI 点评")
        lines.append("")
        try:
            context = {
                "data_as_of": max((a.get("data_as_of") or "") for a in analyses) if analyses else now.strftime("%Y-%m-%d"),
                "market": market,
                "macro": [],
                "funds": [
                    {
                        "fund_profile": {
                            "fund_code": a["fund"]["fund_code"],
                            "fund_name": a["fund"]["fund_name"],
                        },
                        "score": a["score"],
                        "trend": a["trend"],
                        "positive_factors": a.get("positive_factors", []),
                        "negative_factors": a.get("negative_factors", []),
                        "main_risks": a.get("main_risks", []),
                    }
                    for a in analyses
                ],
                "news": top_news,
                "policies": top_policies,
            }
            from app.llm.prompt_builder import SYSTEM_RULES

            system = SYSTEM_RULES.format(data_as_of=context["data_as_of"]) + (
                "\n\n【数据上下文】\n" + "\n".join(
                    f"- {f['fund_profile']['fund_name']}({f['fund_profile']['fund_code']}): 评分{f.get('score', '—')}, "
                    f"趋势 短{f['trend']['short']}/中{f['trend']['medium']}/长{f['trend']['long']}"
                    for f in context["funds"]
                ) + "\n请用 150 字以内总结今日市场与自选基金要点。"
            )
            reply = run_async(
                get_llm_manager().complete(
                    [{"role": "system", "content": system}, {"role": "user", "content": "生成今日市场总结。"}],
                    user_id=user_id,
                )
            )
            lines.append(reply)
        except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
            log.warning("报告 LLM 总结不可用: %s", exc)
            lines.append(
                "LLM 服务不可用，以下为量化引擎摘要："
                + "；".join(
                    f"{a['fund']['fund_name']} 评分 {a['score']}，短期{a['trend']['short']}" for a in analyses
                )
            )
        lines.append("")

    lines.append("---")
    lines.append("*本报告由系统自动生成，仅供参考，不构成投资建议。历史数据不代表未来表现。*")
    content_md = "\n".join(lines)
    report = Report(
        user_id=user_id,
        title=title,
        content_md=content_md,
        content_html=md_lib.markdown(content_md, extensions=["tables"]),
        trigger=trigger,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def report_to_dict(report: Report, include_content: bool = True) -> dict:
    out = {
        "id": report.id,
        "title": report.title,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "trigger": report.trigger,
        "task_id": report.task_id,
    }
    if include_content:
        out["content_md"] = report.content_md
        out["content_html"] = report.content_html
    return out

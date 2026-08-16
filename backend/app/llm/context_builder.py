"""LLM ContextBuilder：自动注入上下文的核心组件。

用户只发一句话，系统后台自动组装：
基金画像 / 行情 / 技术指标 / 风险指标 / 持仓 / 行业暴露 / 预测 / 宏观 / 新闻 / 政策 / 市场环境。
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services import analysis_service, fund_service, market_service, news_service
from app.utils.dates import utcnow

log = get_logger("app.llm")


class ContextBuilder:
    def build(self, fund_ids: list[str], time_range: str = "3M") -> dict:
        """构建多基金 Context。任何子模块失败只置空，不中断整体构建。"""
        context: dict = {
            "generated_at": utcnow().isoformat(),
            "funds": [],
            "market": {},
            "macro": [],
            "news": [],
            "policies": [],
            "data_as_of": None,
        }
        db = SessionLocal()
        try:
            for code in fund_ids:
                fund = fund_service.get_fund_by_code(db, code)
                if fund is None:
                    fund = fund_service.ensure_fund(db, code)
                if fund is None:
                    context["funds"].append(
                        {"fund_code": code, "fund_name": code, "error": "基金信息获取失败"}
                    )
                    continue
                try:
                    analysis = analysis_service.analyze_fund(db, code, time_range, with_prediction=True)
                except Exception as exc:  # noqa: BLE001
                    log.warning("ContextBuilder 基金分析失败 %s: %s", code, exc)
                    analysis = None
                if analysis is not None:
                    context["data_as_of"] = analysis.get("data_as_of")
                context["funds"].append(self._fund_context(db, fund, analysis))
            context["market"] = market_service.market_overview(db)
            context["macro"] = self._macro_context(db)
            context["news"] = news_service.news_list(db, limit=6)
            context["policies"] = news_service.policy_list(db, limit=6)
        finally:
            db.close()
        return context

    # ------------------------------------------------------------ 私有

    def _fund_context(self, db, fund, analysis: dict | None) -> dict:
        profile = {
            "fund_code": fund.fund_code,
            "fund_name": fund.fund_name,
            "fund_type": fund.fund_type,
            "manager": fund.manager,
            "company": fund.company,
            "establish_date": fund.establish_date.isoformat() if fund.establish_date else None,
            "benchmark": fund.benchmark,
            "fund_size": fund.fund_size,
            "risk_level": fund.risk_level,
            "latest_nav": fund.latest_nav,
            "latest_nav_date": fund.latest_nav_date.isoformat() if fund.latest_nav_date else None,
            "source": fund.source,
        }
        if analysis is None:
            return {"fund_profile": profile}
        holdings = analysis.get("holdings") or {}
        returns = fund_service.returns_map(db, fund.id)
        return {
            "fund_profile": profile,
            "performance": {
                "return_1d": returns.get("return_1d"),
                "return_5d": returns.get("return_5d"),
                "return_20d": returns.get("return_20d"),
                "return_60d": returns.get("return_60d"),
                "return_1y": returns.get("return_1y"),
                "return_ytd": returns.get("return_ytd"),
            },
            "technical_indicators": analysis.get("indicators") or {},
            "risk_metrics": analysis.get("risk") or {},
            "holdings": {
                "report_date": holdings.get("report_date"),
                "top10": holdings.get("top10", [])[:5],
                "industry_distribution": holdings.get("industry_distribution", []),
            },
            "prediction": analysis.get("predictions") or {},
            "score": analysis.get("score"),
            "trend": analysis.get("trend") or {},
            "positive_factors": analysis.get("positive_factors") or [],
            "negative_factors": analysis.get("negative_factors") or [],
            "main_risks": analysis.get("main_risks") or [],
            "news": news_service.news_for_fund(db, fund, limit=3),
            "policies": news_service.policies_for_fund(db, fund, limit=3),
            "data_as_of": analysis.get("data_as_of"),
        }

    def _macro_context(self, db) -> list[dict]:
        from app.models import MacroData

        rows = db.query(MacroData).order_by(MacroData.period.desc()).all()
        latest: dict[str, dict] = {}
        for row in rows:
            if row.indicator not in latest:
                latest[row.indicator] = {
                    "indicator": row.indicator,
                    "value": row.value,
                    "unit": row.unit,
                    "period": row.period,
                    "change": row.change,
                    "source": row.source,
                    "published_at": row.published_at.isoformat() if row.published_at else None,
                }
        return list(latest.values())


def build_sources(context: dict) -> dict:
    """数据来源快照（用于「查看本次分析数据来源」）。"""
    funds = [
        {
            "fund_code": f.get("fund_profile", {}).get("fund_code"),
            "fund_name": f.get("fund_profile", {}).get("fund_name"),
            "data_as_of": f.get("data_as_of"),
        }
        for f in context.get("funds", [])
    ]
    return {
        "funds": funds,
        "market": bool(context.get("market", {}).get("indices")),
        "macro": len(context.get("macro", [])),
        "news_count": len(context.get("news", [])),
        "policies_count": len(context.get("policies", [])),
        "prediction": any(f.get("prediction") for f in context.get("funds", [])),
        "data_as_of": context.get("data_as_of"),
        "retrieved_at": context.get("generated_at"),
        "context_version": 1,
    }

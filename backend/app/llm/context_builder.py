"""LLM Context v0.2：领域 Context Provider + 聚合器。

- FundContextProvider / MarketContextProvider / MacroContextProvider /
  NewsContextProvider / PolicyContextProvider / PredictionContextProvider
  → ContextAggregator 统一组装；
- 单 session 复用 + 批查询，避免 N+1；
- data_as_of：每只基金独立 `data_as_of`，全局只保留 `latest_data_as_of`
  （不再被最后一只基金覆盖）；
- 每个 Context 带 context_version + context_hash（规范化内容指纹），
  可证明“当时模型看到的数据到底是什么”。
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.prediction.ledger import snapshot_hash
from app.services import analysis_service, fund_service, market_service, news_service

log = get_logger("app.llm")

CONTEXT_VERSION = 2


class FundContextProvider:
    """基金域：画像/表现/指标/风险/持仓/预测/因子/新闻/政策。"""

    def provide(self, db, code: str, time_range: str) -> dict:
        fund = fund_service.get_fund_by_code(db, code)
        if fund is None:
            fund = fund_service.ensure_fund(db, code)
        if fund is None:
            return {"fund_code": code, "fund_name": code, "error": "基金信息获取失败"}
        try:
            analysis = analysis_service.analyze_fund(db, code, time_range, with_prediction=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("FundContextProvider 分析失败 %s: %s", code, exc)
            analysis = None
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
            return {"fund_profile": profile, "data_as_of": None}
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
            # 每只基金独立的数据时间（修复：不再被其他基金覆盖）
            "data_as_of": analysis.get("data_as_of"),
        }


class MarketContextProvider:
    def provide(self, db) -> dict:
        return market_service.market_overview(db)


class MacroContextProvider:
    def provide(self, db) -> list[dict]:
        from app.models import MacroData
        from app.utils.dates import today

        rows = db.query(MacroData).order_by(MacroData.period.desc()).all()
        latest: dict[str, dict] = {}
        for row in rows:
            if row.indicator not in latest:
                days = (today() - row.published_at).days if row.published_at else None
                latest[row.indicator] = {
                    "indicator": row.indicator,
                    "value": row.value,
                    "unit": row.unit,
                    "period": row.period,
                    "change": row.change,
                    "source": row.source,
                    "published_at": row.published_at.isoformat() if row.published_at else None,
                    "as_of": row.published_at.isoformat() if row.published_at else None,
                    "quality": row.quality
                    or ("high" if days is not None and days <= 60 else ("medium" if days is not None and days <= 180 else "low")),
                }
        return list(latest.values())


class NewsContextProvider:
    def provide(self, db, limit: int = 6) -> list[dict]:
        return news_service.news_list(db, limit=limit)


class PolicyContextProvider:
    def provide(self, db, limit: int = 6) -> list[dict]:
        return news_service.policy_list(db, limit=limit)


class PredictionContextProvider:
    """预测域：模型版本/校准方法/置信度等元信息（概率本体来自量化引擎）。"""

    def provide(self, fund_entries: list[dict]) -> dict:
        out: dict[str, dict] = {}
        for fund in fund_entries:
            predictions = (fund or {}).get("prediction") or {}
            code = (fund or {}).get("fund_profile", {}).get("fund_code")
            if not code or not predictions:
                continue
            summary = {}
            for horizon, pred in predictions.items():
                summary[horizon] = {
                    "model_name": pred.get("model_name"),
                    "model_version": pred.get("model_version"),
                    "calibration_method": pred.get("calibration_method"),
                    "calibrated": pred.get("calibrated"),
                    "confidence": pred.get("confidence"),
                }
            out[code] = summary
        return out


class ContextAggregator:
    """统一 Context 组装：领域 Provider 串行复用同一 session，产出带指纹的 Context。"""

    def __init__(self) -> None:
        self.fund_provider = FundContextProvider()
        self.market_provider = MarketContextProvider()
        self.macro_provider = MacroContextProvider()
        self.news_provider = NewsContextProvider()
        self.policy_provider = PolicyContextProvider()
        self.prediction_provider = PredictionContextProvider()

    def build(self, fund_ids: list[str], time_range: str = "3M") -> dict:
        context: dict = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "context_version": CONTEXT_VERSION,
            "funds": [],
            "market": {},
            "macro": [],
            "news": [],
            "policies": [],
            "latest_data_as_of": None,
        }
        db = SessionLocal()
        try:
            for code in fund_ids:
                context["funds"].append(self.fund_provider.provide(db, code, time_range))
            context["market"] = self.market_provider.provide(db)
            context["macro"] = self.macro_provider.provide(db)
            context["news"] = self.news_provider.provide(db, limit=6)
            context["policies"] = self.policy_provider.provide(db, limit=6)
        finally:
            db.close()
        context["prediction_meta"] = self.prediction_provider.provide(context["funds"])
        # 全局最新数据时间 = 各基金 data_as_of 的最大值（不覆盖、不伪造）
        as_ofs = [
            f.get("data_as_of")
            for f in context["funds"]
            if f.get("data_as_of")
        ]
        context["latest_data_as_of"] = max(as_ofs) if as_ofs else None
        # 内容指纹：剔除易变字段（时间戳/哈希自身），保证同输入同哈希
        stable = {k: v for k, v in context.items() if k not in ("generated_at", "context_hash")}
        context["context_hash"] = snapshot_hash(stable)
        return context


class ContextBuilder:
    """向后兼容入口：v0.2 起内部使用领域 Provider + 聚合器。"""

    def __init__(self) -> None:
        self._aggregator = ContextAggregator()

    def build(self, fund_ids: list[str], time_range: str = "3M") -> dict:
        return self._aggregator.build(fund_ids, time_range)


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
        "data_as_of": context.get("latest_data_as_of"),
        "retrieved_at": context.get("generated_at"),
        "context_version": context.get("context_version"),
        "context_hash": context.get("context_hash"),
    }

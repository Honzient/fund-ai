"""首页 AI 总结：市场环境 + 自选表现 + 驱动因素（LLM 不可用时规则降级）。"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.llm import LLMUnavailableError, get_llm_manager
from app.models import Watchlist
from app.services import analysis_service, fund_service, market_service, news_service
from app.utils.asyncs import run_async
from app.utils.dates import now_local

log = get_logger("app.llm")


def daily_summary(user_id: int) -> dict:
    db = SessionLocal()
    try:
        market = market_service.market_overview(db)
        from app.models import Fund

        watchlist = (
            db.query(Fund)
            .join(Watchlist, Watchlist.fund_id == Fund.id)
            .filter(Watchlist.user_id == user_id)
            .order_by(Watchlist.pinned.desc(), Watchlist.created_at)
            .all()
        )
        summaries = []
        for fund in watchlist:
            summaries.append(fund_service.fund_summary(db, fund, with_score=True))
        if not summaries:
            return {
                "generated_at": now_local().isoformat(),
                "market": market["market_regime"],
                "drivers": market["market_regime"]["drivers"],
                "watchlist": {},
                "text": "自选基金为空。请先添加自选基金，系统将每天自动生成市场与自选总结。",
                "fallback": True,
            }
        best = max(summaries, key=lambda s: s.get("return_1d") or -999)
        worst = min(summaries, key=lambda s: s.get("return_1d") or 999)
        risk_map: dict[str, dict] = {}
        for s in summaries:
            try:
                risk_map[s["fund_code"]] = (
                    analysis_service.analyze_fund(db, s["fund_code"], "3M", with_prediction=False).get(
                        "risk"
                    )
                    or {}
                )
            except Exception:  # noqa: BLE001
                risk_map[s["fund_code"]] = {}
        riskiest = max(
            summaries,
            key=lambda s: risk_map.get(s["fund_code"], {}).get("annual_volatility") or 0,
        )
        watch = [s["fund_code"] for s in summaries if s.get("score") is not None and s["score"] < 50][:3]
        payload = {
            "generated_at": now_local().isoformat(),
            "market": market["market_regime"],
            "drivers": market["market_regime"]["drivers"],
            "watchlist": {
                "best": {k: best.get(k) for k in ("fund_code", "fund_name", "return_1d")},
                "worst": {k: worst.get(k) for k in ("fund_code", "fund_name", "return_1d")},
                "riskiest": {
                    "fund_code": riskiest.get("fund_code"),
                    "fund_name": riskiest.get("fund_name"),
                },
                "focus": watch,
            },
        }
        payload["text"] = _llm_summary(payload, user_id)
        payload["fallback"] = payload["text"].startswith("LLM")
        return payload
    finally:
        db.close()


def _llm_summary(payload: dict, user_id: int) -> str:
    market = payload["market"]
    watch = payload["watchlist"]
    context = (
        f"市场状态：{market['label']}（评分 {market['score']}）。"
        f"驱动因素：{'、'.join(market['drivers'])}。"
        f"自选今日表现最好：{watch['best'].get('fund_name')}（{watch['best'].get('return_1d')}%）；"
        f"表现最差：{watch['worst'].get('fund_name')}（{watch['worst'].get('return_1d')}%）；"
        f"波动最高：{watch['riskiest'].get('fund_name')}。"
    )
    try:
        return run_async(
            get_llm_manager().complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是基金投资研究助手。基于给定数据生成 100 字以内「今日市场 AI 总结」，"
                            "包含：市场环境、今日主要驱动（最多3条）、自选基金表现最好/风险最高/需要重点关注。"
                            "不得编造数据，不得承诺收益，注明仅供参考。"
                        ),
                    },
                    {"role": "user", "content": context},
                ],
                user_id=user_id,
                max_tokens=400,
            )
        ).strip()
    except LLMUnavailableError:
        return (
            "LLM 服务不可用，以下为规则摘要："
            f"市场环境 {market['label']}（{market['score']}分）。"
            f"今日自选表现最好：{watch['best'].get('fund_name')}；"
            f"表现最差：{watch['worst'].get('fund_name')}；"
            f"波动最高：{watch['riskiest'].get('fund_name')}。"
            "仅供参考，不构成投资建议。"
        )

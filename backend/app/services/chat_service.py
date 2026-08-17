"""对话服务：Context 自动注入 + LLM 调用 + 降级摘要 + 会话存储。"""
from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm import ContextBuilder, LLMUnavailableError, build_messages, build_sources, get_llm_manager
from app.models import Conversation, Message, User
from app.utils.asyncs import run_async
from app.utils.dates import utcnow

log = get_logger("app.llm")


def fallback_summary(context: dict, question: str) -> str:
    """LLM 不可用时由量化引擎生成结构化摘要（明确标注）。"""
    lines = [
        "# 量化引擎分析摘要",
        "",
        "> LLM 服务当前不可用，以下内容由本地量化引擎基于最新数据自动生成。",
        "",
        f"数据截至：{context.get('data_as_of') or '未知'}",
        "",
    ]
    regime = (context.get("market") or {}).get("market_regime") or {}
    lines.append(f"**市场环境**：{regime.get('label', '未知')}（评分 {regime.get('score', '—')}）")
    lines.append("")
    for fund in context.get("funds", []):
        if "error" in fund:
            lines.append(f"- {fund.get('fund_code')}：{fund['error']}")
            continue
        profile = fund.get("fund_profile") or {}
        trend = fund.get("trend") or {}
        lines.append(f"## {profile.get('fund_name')}（{profile.get('fund_code')}）")
        lines.append(f"- AI综合评分：**{fund.get('score', '—')}/100**")
        lines.append(
            f"- 趋势：短期 **{trend.get('short', '—')}** / 中期 **{trend.get('medium', '—')}** / "
            f"长期 **{trend.get('long', '—')}**"
        )
        pred = (fund.get("prediction") or {}).get("short") or {}
        probs = pred.get("probabilities") or {}
        if probs:
            lines.append(
                f"- 未来5日概率：上涨 **{probs.get('up', '—')}%** / 震荡 **{probs.get('range', '—')}%** / "
                f"下跌 **{probs.get('down', '—')}%**（置信度：{pred.get('confidence', '—')}）"
            )
        positives = fund.get("positive_factors") or []
        negatives = fund.get("negative_factors") or []
        if positives:
            lines.append("- 正面因素：" + "；".join(p["reason"] for p in positives[:3]))
        if negatives:
            lines.append("- 负面因素：" + "；".join(n["reason"] for n in negatives[:3]))
        risks = fund.get("main_risks") or []
        if risks:
            lines.append("- 主要风险：" + "；".join(f"[{r['category']}]{r['detail']}" for r in risks[:3]))
        lines.append("")
    lines.extend(
        [
            "## 情景分析",
            "- 乐观情景：市场情绪与基本面共振向好，基金净值有望延续修复。",
            "- 基准情景：维持当前趋势与波动水平，净值随市场震荡。",
            "- 悲观情景：宏观/政策/行业出现不利变化，净值回撤风险上升。",
            "",
            "> 以上为基于历史数据的量化估计，仅供参考，不构成投资建议。",
        ]
    )
    return "\n".join(lines)


def handle_chat(
    db,
    user: User,
    message: str,
    fund_ids: list[str],
    conversation_id: str | None = None,
) -> dict:
    """处理一轮对话：后台自动构建 Context 并注入，用户无感知。"""
    conversation = None
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if conversation is None:
            raise ValueError("对话不存在或无权访问")
    if conversation is None:
        conversation = Conversation(id=uuid.uuid4().hex, user_id=user.id, title="新对话", fund_codes=[])
        db.add(conversation)
        db.commit()

    # 1) 后台构建 Context（用户无需手动粘贴任何基金资料）
    context = ContextBuilder().build(fund_ids, "3M")
    # 2) 组装消息：System(规范 + Context) + 历史 + 用户消息
    history_rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(12)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    messages = build_messages(context, history, message)

    # 3) 调用 LLM，失败自动降级
    settings = get_settings()
    reply: str
    model: str
    fallback = False
    try:
        reply = run_async(get_llm_manager().complete(messages, user_id=user.id))
        model = settings.DEEPSEEK_MODEL
    except LLMUnavailableError as exc:
        log.warning("LLM 不可用，降级为量化引擎摘要: %s", exc)
        reply = fallback_summary(context, message)
        model = "rule-engine"
        fallback = True
    except Exception as exc:  # noqa: BLE001
        log.exception("LLM 调用异常: %s", exc)
        reply = fallback_summary(context, message)
        model = "rule-engine"
        fallback = True

    # 4) 保存消息（含 Context 快照，用于数据来源透明）
    db.add(Message(conversation_id=conversation.id, role="user", content=message))
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            context_json=context,
            context_hash=context.get("context_hash"),
            model=model,
        )
    )
    conversation.fund_codes = fund_ids or conversation.fund_codes
    if conversation.title in ("新对话", ""):
        conversation.title = message[:20] + ("…" if len(message) > 20 else "")
    conversation.updated_at = utcnow()
    db.commit()

    return {
        "conversation_id": conversation.id,
        "reply": reply,
        "model": model,
        "fallback": fallback,
        "sources": build_sources(context),
    }


def list_conversations(db, user: User) -> list[dict]:
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )
    out: list[dict] = []
    for conv in rows:
        last = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        out.append(
            {
                "id": conv.id,
                "title": conv.title,
                "fund_codes": conv.fund_codes or [],
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "last_message": (last.content[:60] + "…") if last and len(last.content) > 60 else (last.content if last else None),
            }
        )
    return out


def get_conversation(db, user: User, conversation_id: str) -> dict:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if conv is None:
        raise ValueError("对话不存在或无权访问")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
        .all()
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "fund_codes": conv.fund_codes or [],
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "model": m.model,
            }
            for m in messages
        ],
    }


def get_conversation_sources(db, user: User, conversation_id: str) -> dict:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if conv is None:
        raise ValueError("对话不存在或无权访问")
    last_assistant = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_assistant is None or not last_assistant.context_json:
        return {"available": False}
    return {"available": True, "context": last_assistant.context_json, "sources": build_sources(last_assistant.context_json)}

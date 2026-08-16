"""AI 对话接口：自动 Context 注入。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Conversation, User
from app.schemas.chat import ChatRequest, ConversationCreate
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return chat_service.handle_chat(
            db, user, payload.message, payload.fund_ids, payload.conversation_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return chat_service.list_conversations(db, user)


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = Conversation(
        id=uuid.uuid4().hex,
        user_id=user.id,
        title=payload.title or "新对话",
        fund_codes=payload.fund_ids,
    )
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title, "fund_codes": conv.fund_codes or []}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return chat_service.get_conversation(db, user, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/sources")
def conversation_sources(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看本次分析数据来源（Context 透明性）。"""
    try:
        return chat_service.get_conversation_sources(db, user, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.delete(conv)
    db.commit()
    return {"status": "deleted"}

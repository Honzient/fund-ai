"""自选基金接口：添加 / 删除 / 置顶 / 分组。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Fund, User, Watchlist
from app.schemas.fund import WatchlistCreate, WatchlistUpdate
from app.services import fund_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _item_dict(db: Session, item: Watchlist) -> dict:
    fund = db.get(Fund, item.fund_id)
    return {
        "id": item.id,
        "fund": fund_service.fund_summary(db, fund, with_score=True) if fund else None,
        "group_name": item.group_name,
        "pinned": item.pinned,
        "added_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("")
def list_watchlist(
    group: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Watchlist).filter(Watchlist.user_id == user.id)
    if group:
        q = q.filter(Watchlist.group_name == group)
    items = q.order_by(Watchlist.pinned.desc(), Watchlist.created_at).all()
    return [_item_dict(db, i) for i in items]


@router.get("/groups")
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Watchlist.group_name).filter(Watchlist.user_id == user.id).distinct().all()
    groups = [r[0] for r in rows if r[0]]
    return groups or ["默认"]


@router.post("")
def add_watchlist(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fund = fund_service.ensure_fund(db, payload.fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在或数据源无法获取")
    existing = (
        db.query(Watchlist)
        .filter(Watchlist.user_id == user.id, Watchlist.fund_id == fund.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="该基金已在自选中")
    item = Watchlist(
        user_id=user.id,
        fund_id=fund.id,
        group_name=payload.group_name or "默认",
        pinned=payload.pinned,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_dict(db, item)


@router.patch("/{item_id}")
def update_watchlist(
    item_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.query(Watchlist).filter(Watchlist.id == item_id, Watchlist.user_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="自选记录不存在")
    if payload.group_name is not None:
        item.group_name = payload.group_name
    if payload.pinned is not None:
        item.pinned = payload.pinned
    db.commit()
    db.refresh(item)
    return _item_dict(db, item)


@router.delete("/{item_id}")
def delete_watchlist(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.query(Watchlist).filter(Watchlist.id == item_id, Watchlist.user_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="自选记录不存在")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}

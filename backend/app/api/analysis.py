"""多基金分析 / 预测模型管理 / 回测 / 台账 / 模型健康接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.prediction import HORIZONS
from app.schemas.analysis import AnalysisRequest
from app.services import analysis_service
from app.tasks import get_task_manager

router = APIRouter(tags=["analysis"])


@router.post("/analysis")
def multi_fund_analysis(
    payload: AnalysisRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return analysis_service.compare_funds(db, payload.fund_ids, payload.time_range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/prediction/models")
def prediction_models(_user: User = Depends(get_current_user)):
    from app.prediction.registry import ModelRegistry

    registry = ModelRegistry()
    return registry.list_models()


@router.post("/prediction/retrain")
def retrain(
    horizon: str | None = Query(default=None, pattern="^(short|medium|long)$"),
    _user: User = Depends(get_current_user),
):
    """重新训练（Purged Walk-Forward + 校准 + Champion 更新）。

    后台执行，立即返回 task_id —— 不阻塞 API worker。
    """
    horizons = [horizon] if horizon else list(HORIZONS.keys())

    def _work():
        from app.prediction.retraining import RetrainingManager

        return RetrainingManager(analysis_service.get_engine()).retrain(horizons)

    result = get_task_manager().run("prediction.retrain", _work, retries=0)
    return {"task_id": result["task_id"], "status": "started"}


@router.get("/prediction/backtest/{version}")
def backtest(
    version: str,
    horizon: str = Query(default="short", pattern="^(short|medium|long)$"),
    model_name: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
):
    """Walk-Forward 回测（含 Baseline 对比）。version 仅作标识，可传 latest。"""
    engine = analysis_service.get_engine()
    result = engine.backtest(horizon, version, model_name=model_name)
    if result is None:
        raise HTTPException(status_code=400, detail="训练数据不足，无法回测")
    return result


@router.get("/prediction/health")
def model_health(
    horizon: str | None = Query(default=None, pattern="^(short|medium|long)$"),
    _user: User = Depends(get_current_user),
):
    """模型健康度：Champion + 台账真实命中率 vs 验证期表现 → 状态。"""
    from app.prediction.retraining import RetrainingManager

    return RetrainingManager(analysis_service.get_engine()).health(horizon)


@router.get("/prediction/ledger")
def prediction_ledger(
    fund_code: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """预测台账：预测历史 + 实际结果 + 命中率统计。"""
    from app.prediction.ledger import ledger_history, ledger_stats
    from app.services import fund_service

    fund_id = None
    if fund_code:
        fund = fund_service.get_fund_by_code(db, fund_code)
        if fund is None:
            raise HTTPException(status_code=404, detail="基金不存在")
        fund_id = fund.id
    return {"records": ledger_history(db, fund_id, limit), "stats": ledger_stats(db, fund_id)}


@router.post("/prediction/evaluate")
def evaluate_predictions(_user: User = Depends(get_current_user)):
    """评价待定预测（后台任务：用未来净值回填实际结果）。"""
    from app.prediction.ledger import evaluate_pending

    def _work():
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            return evaluate_pending(session)
        finally:
            session.close()

    result = get_task_manager().run("prediction.evaluate", _work, retries=1)
    return {"task_id": result["task_id"], "status": "started"}

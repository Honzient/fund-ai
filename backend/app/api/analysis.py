"""多基金分析 / 预测模型管理 / 回测 / 台账 / 模型健康接口。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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


@router.post("/prediction/backtest")
def run_backtest(
    payload: dict = Body(default={"horizon": "short", "model_name": None}),
    _user: User = Depends(get_current_user),
):
    """Walk-Forward 回测（含 Baseline 对比）。后台执行，立即返回 task_id。"""
    horizon = str(payload.get("horizon", "short"))
    if horizon not in HORIZONS:
        raise HTTPException(status_code=400, detail=f"未知周期: {horizon}")
    model_name = payload.get("model_name")

    def _work():
        return analysis_service.get_engine().backtest(horizon, "latest", model_name=model_name)

    result = get_task_manager().run("prediction.backtest", _work, retries=0)
    return {"task_id": result["task_id"], "status": "started"}


@router.get("/prediction/backtest/result/{task_id}")
def backtest_result(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """查询回测任务结果（pending/running/success/failed）。"""
    from app.models import TaskRun

    row = db.get(TaskRun, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": row.id,
        "name": row.name,
        "status": row.status,
        "result": row.result,
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


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


@router.get("/prediction/quality")
def prediction_quality(
    horizon: str | None = Query(default=None, pattern="^(short|medium|long)$"),
    fund_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """预测质量分析：预测置信度/类别与未来收益的关系（基于已评价台账）。"""
    from app.prediction.ledger import prediction_quality as quality_fn
    from app.services import fund_service

    fund_id = None
    if fund_code:
        fund = fund_service.get_fund_by_code(db, fund_code)
        if fund is None:
            raise HTTPException(status_code=404, detail="基金不存在")
        fund_id = fund.id
    return quality_fn(db, horizon=horizon, fund_id=fund_id)


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

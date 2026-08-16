"""多基金分析 / 预测模型管理 / 回测接口。"""
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
    """重新训练预测模型（时间序列验证，生成新版本）。"""
    horizons = [horizon] if horizon else list(HORIZONS.keys())

    def _work():
        results = {}
        engine = analysis_service.get_engine()
        for h in horizons:
            meta = engine.train(h)
            results[h] = {"trained": meta is not None, "version": meta["version"] if meta else None,
                          "samples": (meta or {}).get("samples"),
                          "metrics": (meta or {}).get("metrics")}
        return results

    result = get_task_manager().run("prediction.retrain", _work, retries=0)
    return {"task_id": result["task_id"], "status": "started"}


@router.get("/prediction/backtest/{version}")
def backtest(
    version: str,
    horizon: str = Query(default="short", pattern="^(short|medium|long)$"),
    _user: User = Depends(get_current_user),
):
    engine = analysis_service.get_engine()
    result = engine.backtest(horizon, version)
    if result is None:
        raise HTTPException(status_code=400, detail="训练数据不足，无法回测")
    return result

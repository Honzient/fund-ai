"""预测台账（Prediction Ledger）。

每次对外输出预测 → 持久化 PredictionRecord；
未来数据到位后 → 评价任务回填实际收益/实际类别；
由此得到模型的历史真实命中率（模型健康度依据）。
"""
from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.dates import utcnow


class PredictionRecord(Base):
    __tablename__ = "prediction_records"
    __table_args__ = (
        UniqueConstraint("fund_id", "prediction_date", "horizon", name="uq_pred_record"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id", ondelete="CASCADE"), index=True)
    prediction_date: Mapped[date] = mapped_column(Date, index=True)
    horizon: Mapped[str] = mapped_column(String(16))  # short/medium/long
    horizon_days: Mapped[int] = mapped_column(Float, default=5)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calibrated: Mapped[bool] = mapped_column(default=True)
    calibration_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calibrated_probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    predicted_class: Mapped[str | None] = mapped_column(String(16), nullable=True)  # up/range/down
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)  # high/medium/low
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    market_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 评价字段（未来数据到位后回填）
    actual_return: Mapped[float | None] = mapped_column(Float, nullable=True)  # 前向收益 %
    actual_class: Mapped[str | None] = mapped_column(String(16), nullable=True)  # up/range/down
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def record_prediction(db, fund_id: int, payload: dict) -> PredictionRecord:
    """保存一次预测（同基金同预测日同周期去重：保留当日首次）。"""
    from app.utils.dates import parse_date

    prediction_date = parse_date(payload.get("data_as_of"))
    if prediction_date is None:
        prediction_date = date.today()
    existing = (
        db.query(PredictionRecord)
        .filter(
            PredictionRecord.fund_id == fund_id,
            PredictionRecord.prediction_date == prediction_date,
            PredictionRecord.horizon == payload.get("horizon"),
        )
        .first()
    )
    if existing is not None:
        return existing
    raw = payload.get("raw_probabilities") or payload.get("probabilities") or {}
    cal = payload.get("calibrated_probabilities") or payload.get("probabilities") or {}
    record = PredictionRecord(
        fund_id=fund_id,
        prediction_date=prediction_date,
        horizon=payload.get("horizon", "short"),
        horizon_days=int(payload.get("horizon_days", 5)),
        model_name=payload.get("model_name"),
        model_version=payload.get("model_version"),
        calibrated=bool(payload.get("calibrated", False)),
        calibration_method=payload.get("calibration_method"),
        raw_probabilities=raw,
        calibrated_probabilities=cal,
        predicted_class=payload.get("predicted_class"),
        confidence=payload.get("confidence"),
        confidence_score=payload.get("confidence_score"),
        feature_snapshot=payload.get("feature_snapshot"),
        market_snapshot=payload.get("market_snapshot"),
        data_as_of=prediction_date,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def evaluate_pending(db, max_records: int = 2000) -> dict:
    """评价待定预测：对每个未评价记录，用基金净值回填 horizon 日后实际收益与类别。"""
    from app.models import FundDailyData
    from app.prediction.features import TARGET_THRESHOLDS

    records = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.actual_class.is_(None))
        .order_by(PredictionRecord.prediction_date)
        .limit(max_records)
        .all()
    )
    evaluated = 0
    pending = 0
    for record in records:
        navs = (
            db.query(FundDailyData.date, FundDailyData.nav)
            .filter(
                FundDailyData.fund_id == record.fund_id,
                FundDailyData.date >= record.prediction_date,
            )
            .order_by(FundDailyData.date)
            .limit(record.horizon_days + 1)
            .all()
        )
        # 需要预测日 + horizon 日两条净值
        if len(navs) < 2:
            pending += 1
            continue
        start = navs[0]
        candidates = [n for n in navs if (n[0] - start[0]).days >= 5]
        if not candidates:
            pending += 1
            continue
        end = candidates[0]
        ret = (end[1] / start[1] - 1) * 100 if start[1] else None
        if ret is None:
            pending += 1
            continue
        thr = TARGET_THRESHOLDS.get(record.horizon, 0.005)
        cls = "up" if ret > thr * 100 else ("down" if ret < -thr * 100 else "range")
        record.actual_return = round(ret, 4)
        record.actual_class = cls
        record.evaluated_at = utcnow()
        evaluated += 1
    db.commit()
    return {"status": "done", "evaluated": evaluated, "pending": pending}


def ledger_history(db, fund_id: int | None = None, limit: int = 200) -> list[dict]:
    q = db.query(PredictionRecord)
    if fund_id is not None:
        q = q.filter(PredictionRecord.fund_id == fund_id)
    rows = q.order_by(PredictionRecord.prediction_date.desc(), PredictionRecord.id.desc()).limit(limit).all()
    return [_record_dict(r) for r in rows]


def ledger_stats(db, fund_id: int | None = None, windows: tuple = (30, 100, 1000000)) -> dict:
    """模型命中率统计（近30/近100/全部），分模型与总体。"""
    q = db.query(PredictionRecord).filter(PredictionRecord.actual_class.isnot(None))
    if fund_id is not None:
        q = q.filter(PredictionRecord.fund_id == fund_id)
    rows = q.order_by(PredictionRecord.prediction_date.desc()).all()

    def _stats(subset):
        if not subset:
            return None
        hits = sum(1 for r in subset if r.predicted_class == r.actual_class)
        directional = sum(
            1 for r in subset
            if r.predicted_class in ("up", "down") and r.predicted_class == r.actual_class
        )
        directional_total = sum(1 for r in subset if r.predicted_class in ("up", "down"))
        return {
            "count": len(subset),
            "hit_rate": round(hits / len(subset) * 100, 2),
            "directional_hit_rate": round(
                (directional / directional_total * 100) if directional_total else 0, 2
            ),
        }

    overall = {}
    for label, size in (("last_30", 30), ("last_100", 100), ("all", 10**9)):
        overall[label] = _stats(rows[:size])
    by_model: dict[str, dict] = {}
    for r in rows:
        key = f"{r.model_name or 'unknown'} {r.model_version or '?'}"
        by_model.setdefault(key, []).append(r)
    by_model_stats = {k: _stats(v[:100]) for k, v in list(by_model.items())[:10]}
    return {"overall": overall, "by_model": by_model_stats}


# 置信度区间（confidence_score，0-1）
CONFIDENCE_BINS: tuple[tuple[str, float, float], ...] = (
    ("80%+", 0.80, 1.01),
    ("60–80%", 0.60, 0.80),
    ("50–60%", 0.50, 0.60),
    ("<50%", 0.0, 0.50),
)


def _quality_bucket(label: str, subset: list[PredictionRecord]) -> dict:
    """单个分组的质量统计：未来收益分布 + 命中率。"""
    bucket: dict = {"bucket": label, "count": len(subset)}
    if not subset:
        bucket.update(
            {
                "avg_forward_return": None,
                "median_forward_return": None,
                "hit_rate": None,
                "directional_hit_rate": None,
            }
        )
        return bucket
    returns = [r.actual_return for r in subset if r.actual_return is not None]
    hits = sum(1 for r in subset if r.predicted_class == r.actual_class)
    directional = [r for r in subset if r.predicted_class in ("up", "down")]
    dir_hits = sum(1 for r in directional if r.predicted_class == r.actual_class)
    bucket.update(
        {
            "avg_forward_return": round(float(sum(returns) / len(returns)), 4) if returns else None,
            "median_forward_return": round(float(statistics.median(returns)), 4) if returns else None,
            "hit_rate": round(hits / len(subset) * 100, 2),
            "directional_hit_rate": round(dir_hits / len(directional) * 100, 2) if directional else None,
        }
    )
    return bucket


def prediction_quality(
    db,
    horizon: str | None = None,
    fund_id: int | None = None,
) -> dict:
    """预测质量分析：预测概率/置信度与未来收益的关系（基于已评价台账）。

    统计：平均/中位数未来收益、命中率——按置信度区间与预测类别分组。
    只使用 actual_return 已回填的记录；不改动任何台账数据。
    """
    q = db.query(PredictionRecord).filter(PredictionRecord.actual_return.isnot(None))
    if horizon:
        q = q.filter(PredictionRecord.horizon == horizon)
    if fund_id is not None:
        q = q.filter(PredictionRecord.fund_id == fund_id)
    rows = q.all()

    by_confidence: list[dict] = []
    for label, lo, hi in CONFIDENCE_BINS:
        subset = [r for r in rows if r.confidence_score is not None and lo <= r.confidence_score < hi]
        by_confidence.append(_quality_bucket(label, subset))
    unknown_conf = [r for r in rows if r.confidence_score is None]
    by_confidence.append(_quality_bucket("无置信度", unknown_conf))

    by_class: list[dict] = []
    for cls in ("up", "range", "down"):
        subset = [r for r in rows if r.predicted_class == cls]
        by_class.append(_quality_bucket(cls, subset))

    return {
        "sample_count": len(rows),
        "horizon": horizon,
        "by_confidence": [b for b in by_confidence if b["count"] > 0],
        "by_class": [b for b in by_class if b["count"] > 0],
    }


# ---------------------------------------------------------------- 错误环境分析（v0.3）

# 市场状态 label → 标准枚举
_MARKET_LABEL_MAP = {"中性偏多": "bull", "中性偏空": "bear", "中性": "sideways"}

# 技术状态阈值（feature_snapshot.technical）
RSI_HIGH = 70.0
RSI_LOW = 30.0
VOL_HIGH = 0.02  # 20 日波动率 ≥2% → 高波动
VOL_LOW = 0.01  # 20 日波动率 ≤1% → 低波动
DRAWDOWN_LARGE = -0.15  # 60 日回撤 ≤-15% → 大回撤


def _feat_value(record: PredictionRecord, layer: str, col: str):
    """从台账特征快照取数值（快照缺失/结构异常 → None）。"""
    try:
        info = ((record.feature_snapshot or {}).get(layer) or {}).get(col)
        return info.get("value") if isinstance(info, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _market_bucket_of(record: PredictionRecord) -> str:
    try:
        regime = (record.market_snapshot or {}).get("regime") or {}
        return _MARKET_LABEL_MAP.get(regime.get("label"), "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def _rsi_bucket_of(value) -> str:
    if value is None:
        return "missing"
    if value > RSI_HIGH:
        return "rsi>70"
    if value < RSI_LOW:
        return "rsi<30"
    return "rsi_normal"


def _vol_bucket_of(value) -> str:
    if value is None:
        return "missing"
    if value >= VOL_HIGH:
        return "high_volatility"
    if value <= VOL_LOW:
        return "low_volatility"
    return "normal_volatility"


def _drawdown_bucket_of(value) -> str:
    if value is None:
        return "missing"
    if value <= DRAWDOWN_LARGE:
        return "large_drawdown"
    return "normal_drawdown"


def _error_bucket(label: str, subset: list[PredictionRecord]) -> dict:
    """错误环境分组的统计（命中率 + 错误率 + 收益）。"""
    bucket = _quality_bucket(label, subset)
    bucket["error_rate"] = round(100.0 - bucket["hit_rate"], 2) if bucket["hit_rate"] is not None else None
    return bucket


def error_analysis(
    db,
    horizon: str | None = None,
    fund_id: int | None = None,
) -> dict:
    """错误环境分析：模型在什么环境下更容易预测错误（基于已评价台账）。

    维度：市场状态（bull/bear/sideways）、基金类型、置信度、
    技术状态（RSI 超买超卖、波动率、大回撤）。
    只读分析，不修改台账，不影响预测结果。
    """
    from app.models import Fund

    q = (
        db.query(PredictionRecord, Fund)
        .join(Fund, PredictionRecord.fund_id == Fund.id)
        .filter(PredictionRecord.actual_class.isnot(None))
    )
    if horizon:
        q = q.filter(PredictionRecord.horizon == horizon)
    if fund_id is not None:
        q = q.filter(PredictionRecord.fund_id == fund_id)
    rows = q.all()

    def _dimension(dimension: str, buckets: list[tuple[str, list]]) -> dict:
        nonempty = [_error_bucket(label, subset) for label, subset in buckets if subset]
        return {"dimension": dimension, "buckets": nonempty}

    by_market: dict[str, list] = {}
    by_type: dict[str, list] = {}
    by_conf: dict[str, list] = {}
    by_rsi: dict[str, list] = {}
    by_vol: dict[str, list] = {}
    by_dd: dict[str, list] = {}
    for record, fund in rows:
        by_market.setdefault(_market_bucket_of(record), []).append(record)
        by_type.setdefault(fund.fund_type or "unknown", []).append(record)
        by_conf.setdefault(record.confidence or "unknown", []).append(record)
        by_rsi.setdefault(_rsi_bucket_of(_feat_value(record, "technical", "rsi14")), []).append(record)
        by_vol.setdefault(_vol_bucket_of(_feat_value(record, "technical", "vol_20")), []).append(record)
        by_dd.setdefault(_drawdown_bucket_of(_feat_value(record, "technical", "mdd_60")), []).append(record)

    return {
        "sample_count": len(rows),
        "horizon": horizon,
        "environments": [
            _dimension("market_regime", sorted(by_market.items())),
            _dimension("fund_type", sorted(by_type.items())),
            _dimension("confidence", [("high", by_conf.get("high", [])), ("medium", by_conf.get("medium", [])), ("low", by_conf.get("low", [])), ("unknown", by_conf.get("unknown", []))]),
            _dimension("technical_rsi", sorted(by_rsi.items())),
            _dimension("technical_volatility", sorted(by_vol.items())),
            _dimension("technical_drawdown", sorted(by_dd.items())),
        ],
    }


def _record_dict(r: PredictionRecord) -> dict:
    return {
        "id": r.id,
        "fund_id": r.fund_id,
        "prediction_date": r.prediction_date.isoformat(),
        "horizon": r.horizon,
        "horizon_days": r.horizon_days,
        "model_name": r.model_name,
        "model_version": r.model_version,
        "calibrated": r.calibrated,
        "calibration_method": r.calibration_method,
        "raw_probabilities": r.raw_probabilities,
        "calibrated_probabilities": r.calibrated_probabilities,
        "predicted_class": r.predicted_class,
        "confidence": r.confidence,
        "confidence_score": r.confidence_score,
        "data_as_of": r.data_as_of.isoformat() if r.data_as_of else None,
        "actual_return": r.actual_return,
        "actual_class": r.actual_class,
        "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
    }


def snapshot_hash(snapshot: Any) -> str:
    """特征/上下文快照的规范化哈希（context_hash）。"""
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

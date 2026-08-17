"""模型与预测的完整指标体系（分类 / 校准 / 方向性）。"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

CLASS_LABELS = (0, 1, 2)  # 0=down, 1=range, 2=up


def classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray | None = None
) -> dict:
    """多分类指标。y_proba 形状 (n, 3)，列序对应 CLASS_LABELS。"""
    out: dict = {
        "accuracy": round(float((y_true == y_pred).mean()), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "macro_precision": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "macro_recall": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "up_precision": round(float(precision_score(y_true, y_pred, labels=[2], average=None, zero_division=0)[0]), 4),
        "up_recall": round(float(recall_score(y_true, y_pred, labels=[2], average=None, zero_division=0)[0]), 4),
        "down_precision": round(float(precision_score(y_true, y_pred, labels=[0], average=None, zero_division=0)[0]), 4),
        "down_recall": round(float(recall_score(y_true, y_pred, labels=[0], average=None, zero_division=0)[0]), 4),
    }
    if y_proba is not None:
        out["log_loss"] = round(float(log_loss(y_true, y_proba, labels=CLASS_LABELS)), 4)
        out["brier_score"] = round(
            float(np.mean(np.sum((y_proba - np.eye(3)[y_true]) ** 2, axis=1))), 4
        )
        try:
            if len(np.unique(y_true)) >= 2:
                out["roc_auc_ovr"] = round(
                    float(roc_auc_score(y_true, y_proba, multi_class="ovr", labels=CLASS_LABELS)), 4
                )
        except ValueError:
            out["roc_auc_ovr"] = None
    return out


def calibration_metrics(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10) -> dict:
    """校准指标：ECE（期望校准误差）、MCE、分箱可靠性统计。"""
    ece = 0.0
    mce = 0.0
    total = len(y_true)
    bin_stats: list[dict] = []
    for k in CLASS_LABELS:
        probs = y_proba[:, k]
        binary = (y_true == k).astype(int)
        # 按预测概率分箱
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        for b in range(n_bins):
            mask = (probs > bins[b]) & (probs <= bins[b + 1])
            count = int(mask.sum())
            if count == 0:
                continue
            avg_prob = float(probs[mask].mean())
            avg_true = float(binary[mask].mean())
            gap = abs(avg_prob - avg_true)
            ece += count / total * gap
            mce = max(mce, gap)
            bin_stats.append(
                {
                    "class": int(k),
                    "bin_start": round(float(bins[b]), 3),
                    "bin_end": round(float(bins[b + 1]), 3),
                    "count": count,
                    "avg_probability": round(avg_prob, 4),
                    "avg_actual": round(avg_true, 4),
                }
            )
    return {"ece": round(ece, 4), "mce": round(mce, 4), "n_bins": n_bins, "bins": bin_stats}


def directional_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    forward_returns: np.ndarray | None = None,
    up_class: int = 2,
    down_class: int = 0,
) -> dict:
    """方向/交易视角指标：命中率、方向准确率、平均前向收益。"""
    hit_rate = float((y_true == y_pred).mean())
    out: dict = {
        "hit_rate": round(hit_rate, 4),
        "up_hit_rate": None,
        "down_hit_rate": None,
        "avg_forward_return": None,
        "avg_forward_return_when_up": None,
        "avg_forward_return_when_down": None,
    }
    up_mask = y_pred == up_class
    down_mask = y_pred == down_class
    if up_mask.sum() > 0:
        out["up_hit_rate"] = round(float((y_true[up_mask] == up_class).mean()), 4)
    if down_mask.sum() > 0:
        out["down_hit_rate"] = round(float((y_true[down_mask] == down_class).mean()), 4)
    if forward_returns is not None and len(forward_returns) == len(y_pred):
        out["avg_forward_return"] = round(float(np.mean(forward_returns)), 4)
        if up_mask.sum() > 0:
            out["avg_forward_return_when_up"] = round(float(np.mean(forward_returns[up_mask])), 4)
        if down_mask.sum() > 0:
            out["avg_forward_return_when_down"] = round(float(np.mean(forward_returns[down_mask])), 4)
    return out


def model_score(metrics: dict) -> float:
    """ModelScore（0-100）：综合 Brier / LogLoss / BalancedAccuracy / HitRate / ECE。

    不以 Accuracy 作为唯一标准：校准质量与方向稳定性占同等权重。
    """
    brier = metrics.get("brier_score")
    logloss = metrics.get("log_loss")
    bal_acc = metrics.get("balanced_accuracy")
    hit_rate = metrics.get("hit_rate")
    ece = metrics.get("ece")
    score = 0.0
    if brier is not None:
        score += (1.0 - min(brier / 2.0, 1.0)) * 25  # 多分类 Brier 上限 2
    else:
        score += 12.5
    if logloss is not None:
        score += max(0.0, 1.0 - logloss / 1.5) * 20
    else:
        score += 10
    if bal_acc is not None:
        score += max(0.0, bal_acc - 0.3) / 0.7 * 25
    else:
        score += 12.5
    if hit_rate is not None:
        score += max(0.0, hit_rate - 0.3) / 0.7 * 15
    else:
        score += 7.5
    if ece is not None:
        score += (1.0 - min(ece, 1.0)) * 15
    else:
        score += 7.5
    return round(max(0.0, min(score, 100.0)), 2)


def evaluate_model(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray | None,
    forward_returns: np.ndarray | None = None,
) -> dict:
    """一次评测产出完整指标 + ModelScore。"""
    metrics: dict = classification_metrics(y_true, y_pred, y_proba)
    metrics.update(directional_metrics(y_true, y_pred, forward_returns))
    if y_proba is not None:
        metrics.update(calibration_metrics(y_true, y_proba))
    metrics["model_score"] = model_score(metrics)
    return metrics

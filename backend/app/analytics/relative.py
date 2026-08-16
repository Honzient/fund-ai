"""基金 vs 基准：超额收益 / 相对强弱 / Beta / Alpha。"""
from __future__ import annotations

import pandas as pd

from app.analytics.risk import TRADING_DAYS, beta_alpha


def compute_relative(
    fund_nav: pd.DataFrame, benchmark_nav: pd.DataFrame
) -> dict:
    """输入均需 date(升序) + close/nav 列。

    返回：对齐后的日收益、归一化累计序列、超额收益、相对强弱、Beta、Alpha。
    """
    fund = fund_nav.rename(columns={"nav": "close"})[["date", "close"]].copy()
    bench = benchmark_nav[["date", "close"]].copy()
    merged = fund.merge(bench, on="date", suffixes=("_fund", "_bench")).sort_values("date")
    if merged.empty:
        return {"available": False}
    merged["fund_ret"] = merged["close_fund"].pct_change()
    merged["bench_ret"] = merged["close_bench"].pct_change()
    merged = merged.dropna(subset=["fund_ret", "bench_ret"]).reset_index(drop=True)
    if len(merged) < 20:
        return {"available": False}

    base_fund = merged["close_fund"].iloc[0]
    base_bench = merged["close_bench"].iloc[0]
    merged["cum_fund"] = merged["close_fund"] / base_fund
    merged["cum_bench"] = merged["close_bench"] / base_bench
    merged["relative_strength"] = merged["cum_fund"] / merged["cum_bench"] - 1

    excess_return = float(merged["cum_fund"].iloc[-1] - merged["cum_bench"].iloc[-1])
    beta, alpha = beta_alpha(merged["fund_ret"], merged["bench_ret"])

    return {
        "available": True,
        "start": merged["date"].iloc[0].isoformat(),
        "end": merged["date"].iloc[-1].isoformat(),
        "excess_return": round(excess_return * 100, 4),  # 期间累计超额收益 %
        "beta": round(beta, 4),
        "alpha": round(alpha * 100, 4),  # 年化 Alpha %
        "relative_strength_latest": round(float(merged["relative_strength"].iloc[-1]) * 100, 4),
        "series": {
            "date": [d.isoformat() for d in merged["date"]],
            "cum_fund": [round(float(v), 4) for v in merged["cum_fund"]],
            "cum_bench": [round(float(v), 4) for v in merged["cum_bench"]],
            "relative_strength": [round(float(v), 4) for v in merged["relative_strength"]],
        },
    }

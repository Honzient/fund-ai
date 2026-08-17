"""Point-in-Time 数据泄露审计测试（v0.3）。

核心原则：prediction_time = T 时，只允许使用 available_at / published_at <= T 的数据。
覆盖：基金持仓（available_at 截断）、基金规模（历史缺失化）、宏观（发布日期 asof）、
新闻/政策（发布时间截断）。
"""
import hashlib
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.models import Fund, FundHolding, MacroData, News, Policy
from app.prediction.feature_store import FeatureStore, _calendar_aggregate


def _hash(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def test_point_in_time_holdings(db):
    """T 时刻只能看到 available_at <= T 的持仓报告。"""
    fund = Fund(
        fund_code="PITTEST01",
        fund_name="PIT 测试基金",
        fund_type="混合型",
        establish_date=date(2018, 1, 1),
        fund_size=50.0,
        source="test",
    )
    db.add(fund)
    db.flush()
    # 第一期：2023-03-31 报告，2023-05-05 才公开
    for code, w, ind in [("600001", 30.0, "行业A"), ("600002", 20.0, "行业B")]:
        db.add(
            FundHolding(
                fund_id=fund.id, report_date=date(2023, 3, 31), available_at=date(2023, 5, 5),
                stock_code=code, stock_name=code, weight=w, industry=ind, source="test",
            )
        )
    # 第二期：2023-06-30 报告，2023-09-01 才公开
    for code, w, ind in [("600003", 40.0, "行业C"), ("600004", 10.0, "行业D")]:
        db.add(
            FundHolding(
                fund_id=fund.id, report_date=date(2023, 6, 30), available_at=date(2023, 9, 1),
                stock_code=code, stock_name=code, weight=w, industry=ind, source="test",
            )
        )
    db.commit()
    store = FeatureStore()

    # T=2023-07-01：第二期尚未公开 → 只能看到第一期
    st = store._load_fund_static("PITTEST01", as_of=date(2023, 7, 1))  # noqa: SLF001
    assert st["holdings_report_date"] == "2023-03-31"
    assert st["top10_concentration"] == 50.0
    assert st["top_industry"] == "行业A"

    # T=2023-09-05：第二期已公开 → 使用第二期
    st2 = store._load_fund_static("PITTEST01", as_of=date(2023, 9, 5))  # noqa: SLF001
    assert st2["holdings_report_date"] == "2023-06-30"
    assert st2["top10_concentration"] == 50.0
    assert st2["top_industry"] == "行业C"

    # T=2023-04-01：第一期尚未公开 → 无任何持仓可用
    st0 = store._load_fund_static("PITTEST01", as_of=date(2023, 4, 1))  # noqa: SLF001
    assert st0["top10_concentration"] is None
    assert st0["holdings_report_date"] is None

    # 基金年龄按 as_of 计算（不随 today 漂移）
    assert st["fund_age_years"] == pytest.approx(
        (date(2023, 7, 1) - date(2018, 1, 1)).days / 365.25, abs=0.01
    )

    # build_dataset 使用的按日截断路径：每个 T 独立取快照
    idx = pd.DatetimeIndex([pd.Timestamp("2023-07-01"), pd.Timestamp("2023-09-05")])
    top10, _hhi, _topw, inds, ok = store._static_asof(idx, store._load_fund_holdings("PITTEST01"))  # noqa: SLF001
    assert ok.all()
    assert top10[0] == 50.0 and top10[1] == 50.0
    assert inds[0] == "行业A" and inds[1] == "行业C"


def test_point_in_time_fund_size(db):
    """历史训练样本不使用当前规模（无历史规模数据源 → 诚实缺失 + 掩码）。"""
    store = FeatureStore()
    data = store.build_dataset("short")
    assert data is not None
    frame, _y, _dates = data
    assert frame["fund_size"].isna().all(), "训练集 fund_size 必须是缺失（当前值会前向泄露）"
    assert (frame["fund_size_miss"] == 1).all()
    assert frame["top10_concentration_miss"].isin([0, 1]).all()


def test_point_in_time_macro(db):
    """宏观按发布日期截断：T 时刻不使用 published_at > T 的宏观值。"""
    db.add(
        MacroData(
            indicator="CPI同比", period="2099-01", value=99.0,
            published_at=date(2099, 1, 15), source="test",
        )
    )
    db.commit()
    store = FeatureStore()
    series = store._load_macro_series()["macro_cpi"]
    idx = pd.DatetimeIndex([pd.Timestamp("2099-01-14"), pd.Timestamp("2099-01-16")])
    vals = store._asof_values(idx, series)
    assert vals[0] != pytest.approx(99.0), "T 早于发布日期 → 未来值不可见（应取更早的历史值或缺失）"
    assert vals[1] == pytest.approx(99.0), "T 晚于发布日期 → 可见"


def test_point_in_time_news(db):
    """新闻按发布时间截断：T 时刻不使用 published_at > T 的新闻。"""
    db.add(
        News(
            title="PIT 未来新闻", content="不应被历史样本看到",
            published_at=datetime(2099, 1, 16, 9, 0, tzinfo=timezone.utc),
            sentiment=0.9, content_hash=_hash("pit-news-2099"), source="test",
        )
    )
    db.commit()
    store = FeatureStore()
    daily, _counts = store._load_news_daily()
    agg = _calendar_aggregate(daily, 7)
    idx = pd.DatetimeIndex([pd.Timestamp("2099-01-15"), pd.Timestamp("2099-01-17")])
    vals = store._asof_values(idx, agg)
    assert np.isnan(vals[0]), "T 早于新闻发布 → 不可见"
    assert vals[1] == pytest.approx(0.9), "T 晚于新闻发布 → 可见"


def test_point_in_time_policy(db):
    """政策按发布时间截断：T 时刻不使用 published_at > T 的政策。"""
    db.add(
        Policy(
            title="PIT 未来政策", content="不应被历史样本看到",
            published_at=datetime(2099, 1, 16, 9, 0, tzinfo=timezone.utc),
            sentiment=0.7, importance=0.8, content_hash=_hash("pit-policy-2099"), source="test",
        )
    )
    db.commit()
    store = FeatureStore()
    pol_s, _pol_i, _pol_c = store._load_policy_daily()
    agg = _calendar_aggregate(pol_s, 30)
    idx = pd.DatetimeIndex([pd.Timestamp("2099-01-15"), pd.Timestamp("2099-01-17")])
    vals = store._asof_values(idx, agg)
    assert np.isnan(vals[0]), "T 早于政策发布 → 不可见"
    assert vals[1] == pytest.approx(0.7), "T 晚于政策发布 → 可见"

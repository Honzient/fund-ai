"""Feature Store / 数据溯源 / 行业分类 / 缺失语义 测试。"""
from datetime import date, timedelta

import numpy as np
import pytest

from app.models import News, Policy, SecurityIndustry
from app.prediction.feature_store import LAYER_COLUMNS, MASKED_LAYERS, FeatureStore


def test_feature_columns_with_masks():
    store = FeatureStore()
    cols = store.feature_columns
    for layer in MASKED_LAYERS:
        for col in LAYER_COLUMNS[layer]:
            assert f"{col}_miss" in cols
    # 技术层没有 mask（净值数据必有）
    assert "rsi14_miss" not in cols


def test_missing_masks_are_explicit():
    import pandas as pd

    store = FeatureStore()
    df = pd.DataFrame(
        {
            "ret_1": [0.0, 0.01], "ret_5": [0.0, 0.0], "ret_20": [0.0, 0.0],
            "ret_60": [0.0, 0.0], "rsi14": [50.0, 51.0], "macd_hist_norm": [0.0, 0.1],
            "bb_position": [0.0, 0.0], "vol_20": [0.01, 0.02],
            "dist_ma20": [0.0, 0.0], "dist_ma60": [0.0, 0.0], "mdd_60": [-0.1, -0.1],
            "market_ret_5": [0.0, 0.0], "market_ret_20": [0.0, 0.0], "market_rsi14": [50.0, 50.0],
            "news_sentiment_7d": [np.nan, 0.3],
        }
    )
    store._add_missing_masks(df)
    assert df["news_sentiment_7d_miss"].tolist() == [1, 0]
    assert df["macro_pmi_miss"] is not None or "macro_pmi_miss" in df.columns


def test_news_quality_and_provenance(db):
    from app.services.news_service import _as_of, _quality_of, _news_dict
    from app.utils.dates import utcnow

    news = News(
        title="测试新闻", content="内容", source="test-source", url="https://example.com",
        published_at=utcnow(), sentiment=0.5, importance=0.7, content_hash="h1",
        quality="high", as_of=date.today(),
    )
    db.add(news)
    db.commit()
    d = _news_dict(news)
    assert d["source"] == "test-source"
    assert d["url"] == "https://example.com"
    assert d["quality"] == "high"
    assert d["as_of"] == date.today().isoformat()


def test_stale_data_detection():
    from app.services.news_service import _quality_of
    from app.utils.dates import utcnow

    import datetime as dt

    fresh = _quality_of(utcnow())
    assert fresh == "high"
    old = _quality_of(utcnow() - dt.timedelta(days=100))
    assert old == "low"


def test_unknown_industry(db):
    """未知股票 → industry_of 返回 None → 服务层标注 unknown（不强行分类）。"""
    from app.models import industry_of

    db.add(SecurityIndustry(security_code="600000", industry="银行", taxonomy="builtin", source="builtin"))
    db.commit()
    assert industry_of(db, "600000") == "银行"
    assert industry_of(db, "999999") is None  # 无记录 → unknown（由调用方标注）


def test_industry_taxonomy_fields(db):
    from app.models import industry_of

    db.add(
        SecurityIndustry(
            security_code="000001", security_name="平安银行", market="CN",
            industry="银行", taxonomy="申万", valid_from=date(2020, 1, 1),
            valid_to=date(2030, 1, 1), source="sw2021",
        )
    )
    db.commit()
    assert industry_of(db, "000001") == "银行"
    assert industry_of(db, "000001", taxonomy="申万") == "银行"
    assert industry_of(db, "000001", taxonomy="GICS") is None


def test_provider_fallback_registry():
    """Provider 注册表：第一个 Provider 空结果 → 自动 fallback 到下一个。"""
    import asyncio

    from app.providers.base import DataProvider
    from app.providers.registry import ProviderRegistry
    from app.cache.cache import TTLCache

    class Empty(DataProvider):
        name = "empty"

        async def search_funds(self, keyword, limit=20):
            return []

        async def get_fund_info(self, fund_code):
            return None

        async def get_nav_history(self, fund_code, start=None, end=None):
            return []

    class Good(DataProvider):
        name = "good"

        async def search_funds(self, keyword, limit=20):
            from app.providers.base import FundSearchItem

            return [FundSearchItem(fund_code="123456", fund_name="好基金", source="good")]

        async def get_fund_info(self, fund_code):
            from app.providers.base import FundInfo

            return FundInfo(fund_code="123456", fund_name="好基金", source="good")

        async def get_nav_history(self, fund_code, start=None, end=None):
            from app.providers.base import NavPoint

            return [NavPoint(date=date.today(), nav=1.0, source="good")]

    registry = ProviderRegistry([Empty(), Good()], cache=TTLCache())
    result = asyncio.run(registry.call("search_funds", keyword="x"))
    assert result[0].source == "good"
    info = asyncio.run(registry.call("get_fund_info", fund_code="123456"))
    assert info.source == "good"

"""分层 Feature Store：所有模型只能从 FeatureSnapshot 读取特征。

层次：technical / market / macro / industry / sentiment / policy / fundamental。
缺失语义：数据缺失 → NaN + 显式 `{col}_miss` 掩码列，绝不隐式填 0。
填充/标准化只在 fold 内用训练集统计量完成（见 engine），本模块不跨期处理。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.indicators import rsi
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Fund, FundDailyData, FundHolding, MacroData, MarketIndexData, News, Policy
from app.utils.dates import parse_date, today

log = get_logger("app.prediction")

FEATURE_VERSION = "v0.2.0"
DATASET_VERSION = "v0.2.0"

TECHNICAL_COLUMNS = [
    "ret_1", "ret_5", "ret_20", "ret_60",
    "rsi14", "macd_hist_norm", "bb_position", "vol_20",
    "dist_ma20", "dist_ma60", "mdd_60",
]
MARKET_COLUMNS = ["market_ret_5", "market_ret_20", "market_rsi14"]
MACRO_COLUMNS = [
    "macro_pmi", "macro_cpi", "macro_ppi", "macro_m2",
    "macro_lpr1y", "macro_usdcny", "macro_yield10y", "macro_social_financing",
]
INDUSTRY_COLUMNS = ["industry_news_sentiment_7d", "industry_policy_sentiment_30d", "industry_weight_top"]
SENTIMENT_COLUMNS = ["news_sentiment_7d", "news_count_7d"]
POLICY_COLUMNS = ["policy_sentiment_30d", "policy_importance_30d", "policy_count_30d"]
FUNDAMENTAL_COLUMNS = ["fund_size", "fund_age_years", "top10_concentration", "industry_hhi"]

LAYER_COLUMNS: dict[str, list[str]] = {
    "technical": TECHNICAL_COLUMNS,
    "market": MARKET_COLUMNS,
    "macro": MACRO_COLUMNS,
    "industry": INDUSTRY_COLUMNS,
    "sentiment": SENTIMENT_COLUMNS,
    "policy": POLICY_COLUMNS,
    "fundamental": FUNDAMENTAL_COLUMNS,
}

MASKED_LAYERS = ("macro", "industry", "sentiment", "policy")

_MACRO_KEY_MAP = {
    "制造业PMI": "macro_pmi",
    "CPI同比": "macro_cpi",
    "PPI同比": "macro_ppi",
    "M2同比": "macro_m2",
    "1年期LPR": "macro_lpr1y",
    "美元兑人民币": "macro_usdcny",
    "10年期国债收益率": "macro_yield10y",
    "社会融资规模": "macro_social_financing",
}


def _calendar_aggregate(daily: pd.Series, window_days: int) -> pd.Series:
    """日历窗口均值聚合：窗口内只用已发生数据（rolling 天然无未来）。"""
    if daily is None or len(daily) == 0:
        return pd.Series(dtype=float)
    cal = daily.resample("D").mean()
    full = cal.reindex(pd.date_range(cal.index.min(), cal.index.max(), freq="D"))
    return full.rolling(f"{window_days}D", min_periods=1).mean()


def _count_aggregate(daily: pd.Series, window_days: int) -> pd.Series:
    """日历窗口计数聚合。"""
    if daily is None or len(daily) == 0:
        return pd.Series(dtype=float)
    cal = daily.resample("D").sum(min_count=1).fillna(0)
    full = cal.reindex(pd.date_range(cal.index.min(), cal.index.max(), freq="D"), fill_value=0)
    return full.rolling(f"{window_days}D", min_periods=1).sum()


class FeatureStore:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    # ------------------------------------------------------------ 数据加载

    def _load_fund_histories(self, years: float = 4.0) -> dict[str, pd.DataFrame]:
        db = SessionLocal()
        try:
            start = date.today() - timedelta(days=int(years * 365))
            rows = (
                db.query(FundDailyData, Fund.fund_code)
                .join(Fund, FundDailyData.fund_id == Fund.id)
                .filter(FundDailyData.date >= start)
                .order_by(FundDailyData.date)
                .all()
            )
            frames: dict[str, list[tuple[date, float]]] = {}
            for row, code in rows:
                frames.setdefault(code, []).append((row.date, float(row.nav)))
            out: dict[str, pd.DataFrame] = {}
            for code, items in frames.items():
                if len(items) >= 120:
                    out[code] = pd.DataFrame(items, columns=["date", "nav"])
            return out
        finally:
            db.close()

    def _load_market_series(self, years: float = 4.0) -> pd.Series | None:
        db = SessionLocal()
        try:
            start = date.today() - timedelta(days=int(years * 365))
            rows = (
                db.query(MarketIndexData)
                .join(MarketIndexData.index)
                .filter_by(index_code="000300")
                .filter(MarketIndexData.date >= start)
                .order_by(MarketIndexData.date)
                .all()
            )
            if not rows:
                return None
            return pd.Series(
                [float(r.close) for r in rows],
                index=pd.DatetimeIndex([pd.Timestamp(r.date) for r in rows], name="date"),
            )
        finally:
            db.close()

    def _load_macro_series(self) -> dict[str, pd.Series]:
        """指标名 → 以发布日期为索引的月度值序列。"""
        db = SessionLocal()
        try:
            rows = db.query(MacroData).order_by(MacroData.published_at).all()
        finally:
            db.close()
        out: dict[str, pd.Series] = {}
        for r in rows:
            if r.published_at is None:
                continue
            col = _MACRO_KEY_MAP.get(r.indicator)
            if col is None:
                continue
            out.setdefault(col, {})[pd.Timestamp(r.published_at)] = float(r.value)
        return {k: pd.Series(v).sort_index() for k, v in out.items()}

    def _load_news_daily(self) -> tuple[pd.Series, pd.Series]:
        """(每日平均情绪, 每日新闻数)，索引为自然日。"""
        db = SessionLocal()
        try:
            rows = (
                db.query(News.published_at, News.sentiment, News.related_industry)
                .filter(News.published_at.isnot(None))
                .all()
            )
        finally:
            db.close()
        if not rows:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        df = pd.DataFrame(
            [
                (pd.Timestamp(r[0].date()), float(r[1] or 0), r[2])
                for r in rows
                if r[0] is not None
            ],
            columns=["day", "sentiment", "industry"],
        )
        daily = df.groupby("day")["sentiment"].mean()
        counts = df.groupby("day")["sentiment"].count()
        return daily, counts

    def _load_policy_daily(self) -> tuple[pd.Series, pd.Series, pd.Series]:
        """(每日平均情绪, 每日平均重要度, 每日政策数)。"""
        db = SessionLocal()
        try:
            rows = (
                db.query(Policy.published_at, Policy.sentiment, Policy.importance, Policy.related_industry)
                .filter(Policy.published_at.isnot(None))
                .all()
            )
        finally:
            db.close()
        if not rows:
            empty = pd.Series(dtype=float)
            return empty, empty, empty
        df = pd.DataFrame(
            [
                (pd.Timestamp(r[0].date()), float(r[1] or 0), float(r[2] or 0), r[3])
                for r in rows
                if r[0] is not None
            ],
            columns=["day", "sentiment", "importance", "industry"],
        )
        return (
            df.groupby("day")["sentiment"].mean(),
            df.groupby("day")["importance"].mean(),
            df.groupby("day")["sentiment"].count(),
        )

    def _load_industry_daily(self) -> dict[str, tuple[pd.Series, pd.Series]]:
        """行业 → (新闻每日情绪, 政策每日情绪)。"""
        db = SessionLocal()
        try:
            news_rows = (
                db.query(News.published_at, News.sentiment, News.related_industry)
                .filter(News.published_at.isnot(None), News.related_industry.isnot(None))
                .all()
            )
            policy_rows = (
                db.query(Policy.published_at, Policy.sentiment, Policy.related_industry)
                .filter(Policy.published_at.isnot(None), Policy.related_industry.isnot(None))
                .all()
            )
        finally:
            db.close()
        out: dict[str, tuple[pd.Series, pd.Series]] = {}
        for label, rows in (("news", news_rows), ("policy", policy_rows)):
            data: dict[str, dict[pd.Timestamp, list[float]]] = {}
            for published, sentiment, industry in rows:
                if published is None:
                    continue
                data.setdefault(industry, {}).setdefault(pd.Timestamp(published.date()), []).append(
                    float(sentiment or 0)
                )
            for industry, day_map in data.items():
                series = pd.Series({k: float(np.mean(v)) for k, v in day_map.items()}).sort_index()
                existing = out.setdefault(industry, (pd.Series(dtype=float), pd.Series(dtype=float)))
                if label == "news":
                    out[industry] = (series, existing[1])
                else:
                    out[industry] = (existing[0], series)
        return out

    def _load_fund_static(self, code: str) -> dict:
        db = SessionLocal()
        try:
            fund = db.query(Fund).filter(Fund.fund_code == code).first()
            if fund is None:
                return {}
            age = 0.0
            if fund.establish_date:
                age = max(0.0, (today() - fund.establish_date).days / 365.25)
            holdings = (
                db.query(FundHolding)
                .filter(FundHolding.fund_id == fund.id)
                .order_by(FundHolding.report_date.desc(), FundHolding.weight.desc())
                .all()
            )
            top10 = 0.0
            industries: dict[str, float] = {}
            report_date = None
            if holdings:
                report_date = holdings[0].report_date
                top = [h for h in holdings if h.report_date == report_date][:10]
                top10 = round(sum(h.weight or 0 for h in top), 2)
                for h in top:
                    industry = h.industry or "unknown"
                    industries[industry] = industries.get(industry, 0.0) + (h.weight or 0)
            hhi = round(sum((w / 100) ** 2 for w in industries.values()), 4) if industries else None
            top_industry = max(industries, key=industries.get) if industries else None
            return {
                "fund_size": fund.fund_size,
                "fund_age_years": round(age, 2),
                "top10_concentration": top10,
                "industry_hhi": hhi,
                "industries": industries,
                "top_industry": top_industry,
                "top_industry_weight": industries.get(top_industry) if top_industry else None,
                "holdings_report_date": report_date.isoformat() if report_date else None,
            }
        finally:
            db.close()

    # ------------------------------------------------------------ 数据集

    def build_dataset(
        self, horizon: str, years: float = 4.0, min_history: int = 140
    ) -> tuple[pd.DataFrame, np.ndarray, np.ndarray] | None:
        """组装全市场训练数据集：X 帧 + 标签 + 日期。"""
        from app.prediction.features import HORIZONS, TARGET_THRESHOLDS, add_features, make_labels

        funds = self._load_fund_histories(years)
        if not funds:
            return None
        market = self._load_market_series(years)
        macro = self._load_macro_series()
        news_s, news_c = self._load_news_daily()
        pol_s, pol_i, pol_c = self._load_policy_daily()
        industry_daily = self._load_industry_daily()
        static = {code: self._load_fund_static(code) for code in funds}

        h = HORIZONS[horizon]
        frames: list[pd.DataFrame] = []
        for code, df in funds.items():
            if len(df) < min_history:
                continue
            feats = add_features(df.sort_values("date"), market)
            idx = pd.DatetimeIndex(feats["date"])
            # 市场 RSI（对齐到基金交易日）
            if market is not None and len(market) > 20:
                market_rsi = rsi(market, 14).rename("market_rsi14")
                feats = self._asof_join(feats, idx, market_rsi)
            else:
                feats["market_rsi14"] = np.nan
            # 宏观（按发布日期 asof）
            for col, series in macro.items():
                feats[col] = self._asof_values(idx, series)
            # 行业（基金第一大行业）
            st = static.get(code, {})
            top_industry = st.get("top_industry")
            if top_industry and top_industry in industry_daily:
                ind_news, ind_pol = industry_daily[top_industry]
                feats["industry_news_sentiment_7d"] = self._asof_values(
                    idx, _calendar_aggregate(ind_news, 7) if not ind_news.empty else pd.Series(dtype=float)
                )
                feats["industry_policy_sentiment_30d"] = self._asof_values(
                    idx, _calendar_aggregate(ind_pol, 30) if not ind_pol.empty else pd.Series(dtype=float)
                )
            else:
                feats["industry_news_sentiment_7d"] = np.nan
                feats["industry_policy_sentiment_30d"] = np.nan
            feats["industry_weight_top"] = st.get("top_industry_weight")
            # 情绪 / 政策
            feats["news_sentiment_7d"] = self._asof_values(idx, _calendar_aggregate(news_s, 7))
            feats["news_count_7d"] = self._asof_values(idx, _count_aggregate(news_c, 7))
            feats["policy_sentiment_30d"] = self._asof_values(idx, _calendar_aggregate(pol_s, 30))
            feats["policy_importance_30d"] = self._asof_values(idx, _calendar_aggregate(pol_i, 30))
            feats["policy_count_30d"] = self._asof_values(idx, _count_aggregate(pol_c, 30))
            # 基本面（静态）
            feats["fund_size"] = st.get("fund_size")
            feats["fund_age_years"] = st.get("fund_age_years")
            feats["top10_concentration"] = st.get("top10_concentration")
            feats["industry_hhi"] = st.get("industry_hhi")
            # 标签与前向收益
            price = feats["nav"]
            future_ret = price.shift(-h) / price - 1
            feats["label"] = make_labels(future_ret, horizon)
            feats["fwd_ret"] = future_ret
            feats["fund_code"] = code
            frames.append(feats)
        if not frames:
            return None
        all_df = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
        value_cols = [c for layer in LAYER_COLUMNS.values() for c in layer]
        # 数据源缺失的层次：显式补 NaN 列（缺失 ≠ 0）
        for col in value_cols:
            if col not in all_df.columns:
                all_df[col] = np.nan
        mask_cols = self._add_missing_masks(all_df)
        keep = value_cols + mask_cols + ["date", "fund_code", "label", "fwd_ret"]
        all_df = all_df.dropna(subset=["label"] + TECHNICAL_COLUMNS + MARKET_COLUMNS)
        if all_df.empty:
            return None
        y = all_df["label"].to_numpy(dtype=int)
        dates = all_df["date"].to_numpy()
        return all_df[keep], y, dates

    @property
    def feature_columns(self) -> list[str]:
        cols = [c for layer in LAYER_COLUMNS.values() for c in layer]
        return cols + [f"{c}_miss" for layer in MASKED_LAYERS for c in LAYER_COLUMNS[layer]]

    def _add_missing_masks(self, df: pd.DataFrame) -> list[str]:
        mask_cols: list[str] = []
        for layer in MASKED_LAYERS:
            for col in LAYER_COLUMNS[layer]:
                if col not in df.columns:
                    df[col] = np.nan  # 数据源缺失的层次：NaN（缺失 ≠ 0）
                mask = col + "_miss"
                df[mask] = df[col].isna().astype(int)
                mask_cols.append(mask)
        return mask_cols

    @staticmethod
    def _asof_values(idx: pd.DatetimeIndex, series: pd.Series) -> pd.Series:
        """按 idx 取 series 最近已知值（merge_asof backward；无未来）。"""
        if series is None or len(series) == 0:
            return pd.Series(np.nan, index=range(len(idx)))
        left = pd.DatetimeIndex(idx).as_unit("ns")
        right = pd.DatetimeIndex(series.index).as_unit("ns")
        s = pd.Series(series.to_numpy(), index=right)
        merged = pd.merge_asof(
            pd.DataFrame({"date": left}),
            s.rename("v").reset_index().rename(columns={"index": "date"}),
            on="date",
            direction="backward",
        )
        return pd.Series(merged["v"].to_numpy(), index=range(len(idx)))

    @staticmethod
    def _asof_join(df: pd.DataFrame, idx: pd.DatetimeIndex, series: pd.Series) -> pd.DataFrame:
        left = pd.DatetimeIndex(idx).as_unit("ns")
        right = pd.DatetimeIndex(series.index).as_unit("ns")
        s = pd.Series(series.to_numpy(), index=right)
        merged = pd.merge_asof(
            pd.DataFrame({"date": left}),
            s.rename("v").reset_index().rename(columns={"index": "date"}),
            on="date",
            direction="backward",
        )
        df[series.name or "v"] = merged["v"].to_numpy()
        return df

    # ------------------------------------------------------------ 当前快照

    def current_feature_row(self, fund_code: str) -> tuple[dict, dict] | None:
        """当前时点特征行 + 带质量的 FeatureSnapshot（供预测与 LLM）。"""
        frame, y, dates = self._build_single_fund_frame(fund_code)
        if frame is None or frame.empty:
            return None, None
        row_df = frame.dropna(subset=TECHNICAL_COLUMNS + MARKET_COLUMNS)
        if row_df.empty:
            return None, None
        latest = row_df.iloc[-1]
        row = {col: (None if pd.isna(latest[col]) else float(latest[col])) for col in self.feature_columns}
        snapshot = self._snapshot_from_row(latest, fund_code)
        return row, snapshot

    def _build_single_fund_frame(self, fund_code: str) -> tuple[pd.DataFrame | None, np.ndarray, np.ndarray]:
        from app.prediction.features import add_features, make_labels

        funds = self._load_fund_histories(4.0)
        if fund_code not in funds:
            return None, np.array([]), np.array([])
        df = funds[fund_code]
        market = self._load_market_series(4.0)
        feats = add_features(df.sort_values("date"), market)
        idx = pd.DatetimeIndex(feats["date"])
        if market is not None and len(market) > 20:
            feats = self._asof_join(feats, idx, rsi(market, 14).rename("market_rsi14"))
        else:
            feats["market_rsi14"] = np.nan
        macro = self._load_macro_series()
        for col, series in macro.items():
            feats[col] = self._asof_values(idx, series)
        news_s, news_c = self._load_news_daily()
        pol_s, pol_i, pol_c = self._load_policy_daily()
        industry_daily = self._load_industry_daily()
        st = self._load_fund_static(fund_code)
        top_industry = st.get("top_industry")
        if top_industry and top_industry in industry_daily:
            ind_news, ind_pol = industry_daily[top_industry]
            feats["industry_news_sentiment_7d"] = self._asof_values(
                idx, _calendar_aggregate(ind_news, 7) if not ind_news.empty else pd.Series(dtype=float)
            )
            feats["industry_policy_sentiment_30d"] = self._asof_values(
                idx, _calendar_aggregate(ind_pol, 30) if not ind_pol.empty else pd.Series(dtype=float)
            )
        else:
            feats["industry_news_sentiment_7d"] = np.nan
            feats["industry_policy_sentiment_30d"] = np.nan
        feats["industry_weight_top"] = st.get("top_industry_weight")
        feats["news_sentiment_7d"] = self._asof_values(idx, _calendar_aggregate(news_s, 7))
        feats["news_count_7d"] = self._asof_values(idx, _count_aggregate(news_c, 7))
        feats["policy_sentiment_30d"] = self._asof_values(idx, _calendar_aggregate(pol_s, 30))
        feats["policy_importance_30d"] = self._asof_values(idx, _calendar_aggregate(pol_i, 30))
        feats["policy_count_30d"] = self._asof_values(idx, _count_aggregate(pol_c, 30))
        feats["fund_size"] = st.get("fund_size")
        feats["fund_age_years"] = st.get("fund_age_years")
        feats["top10_concentration"] = st.get("top10_concentration")
        feats["industry_hhi"] = st.get("industry_hhi")
        feats["fund_code"] = fund_code
        # 数据源缺失的层次：显式补 NaN 列（缺失 ≠ 0）
        for col in [c for layer in LAYER_COLUMNS.values() for c in layer]:
            if col not in feats.columns:
                feats[col] = np.nan
        self._add_missing_masks(feats)
        y = np.array([])
        dates = feats["date"].to_numpy()
        return feats, y, dates

    def _snapshot_from_row(self, latest: pd.Series, fund_code: str) -> dict:
        """带 quality/source/as_of 的 FeatureSnapshot。"""
        db = SessionLocal()
        try:
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            latest_nav_date = fund.latest_nav_date if fund else None
            macro_meta = self._macro_provenance(db)
            news_latest = (
                db.query(News.published_at).filter(News.published_at.isnot(None)).order_by(News.published_at.desc()).first()
            )
            policy_latest = (
                db.query(Policy.published_at).filter(Policy.published_at.isnot(None)).order_by(Policy.published_at.desc()).first()
            )
        finally:
            db.close()

        snapshot: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fund_code": fund_code,
            "feature_version": FEATURE_VERSION,
            "layers": {},
        }
        for layer, cols in LAYER_COLUMNS.items():
            layer_data: dict[str, Any] = {}
            for col in cols:
                value = latest.get(col)
                if value is None or (isinstance(value, float) and np.isnan(value)):
                    layer_data[col] = {"value": None, "quality": "missing", "source": None, "as_of": None}
                else:
                    layer_data[col] = {
                        "value": round(float(value), 6),
                        "quality": self._layer_quality(layer, macro_meta, news_latest, policy_latest),
                        "source": self._layer_source(layer),
                        "as_of": self._layer_as_of(layer, latest_nav_date, macro_meta, news_latest, policy_latest),
                    }
            snapshot["layers"][layer] = layer_data
        snapshot["as_of"] = latest_nav_date.isoformat() if latest_nav_date else None
        return snapshot

    @staticmethod
    def _macro_provenance(db) -> dict[str, dict]:
        rows = db.query(MacroData).order_by(MacroData.period.desc()).all()
        latest: dict[str, dict] = {}
        for r in rows:
            if r.indicator not in latest:
                latest[r.indicator] = {
                    "value": r.value, "published_at": r.published_at, "source": r.source,
                }
        return latest

    @staticmethod
    def _layer_source(layer: str) -> str:
        return {
            "technical": "fund_daily",
            "market": "market_index",
            "macro": "macro_data",
            "industry": "news+policy+holdings",
            "sentiment": "news",
            "policy": "policy",
            "fundamental": "fund+holdings",
        }.get(layer, "unknown")

    @staticmethod
    def _layer_quality(layer: str, macro_meta, news_latest, policy_latest) -> str:
        if layer in ("technical", "market", "fundamental"):
            return "high"
        if layer == "macro":
            dates = [m["published_at"] for m in macro_meta.values() if m.get("published_at")]
            if not dates:
                return "missing"
            newest = max(dates)
            days = (today() - newest).days
            return "high" if days <= 60 else ("medium" if days <= 180 else "low")
        if layer in ("sentiment", "industry"):
            if news_latest is None:
                return "missing"
            days = (datetime.now(timezone.utc).date() - news_latest[0].date()).days
            return "high" if days <= 7 else ("medium" if days <= 30 else "low")
        if layer == "policy":
            if policy_latest is None:
                return "missing"
            days = (datetime.now(timezone.utc).date() - policy_latest[0].date()).days
            return "high" if days <= 30 else ("medium" if days <= 90 else "low")
        return "medium"

    @staticmethod
    def _layer_as_of(layer: str, latest_nav_date, macro_meta, news_latest, policy_latest) -> str | None:
        if layer in ("technical", "market"):
            return latest_nav_date.isoformat() if latest_nav_date else None
        if layer == "macro":
            dates = [m["published_at"] for m in macro_meta.values() if m.get("published_at")]
            return max(dates).isoformat() if dates else None
        if layer in ("sentiment", "industry"):
            return news_latest[0].date().isoformat() if news_latest else None
        if layer == "policy":
            return policy_latest[0].date().isoformat() if policy_latest else None
        return None

    def market_snapshot(self) -> dict:
        """市场快照（供台账与上下文）。"""
        from app.services import market_service

        db = SessionLocal()
        try:
            overview = market_service.market_overview(db)
            return {
                "regime": overview.get("market_regime"),
                "breadth": overview.get("breadth"),
                "generated_at": overview.get("generated_at"),
            }
        finally:
            db.close()

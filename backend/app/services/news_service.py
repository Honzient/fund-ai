"""新闻/政策服务：同步（去重/情绪/行业映射/重要性）与查询聚合。"""
from __future__ import annotations

import hashlib

from app.analytics.sentiment import detect_industries, importance_score, score_text, sentiment_label
from app.core.logging import get_logger
from app.models import Fund, FundHolding, News, Policy
from app.providers import get_registry
from app.utils.asyncs import run_async
from app.utils.dates import utcnow

log = get_logger("app.data")


def _content_hash(title: str, source: str) -> str:
    return hashlib.sha1(f"{title}|{source}".encode("utf-8")).hexdigest()


def sync_news(db, limit: int = 60) -> dict:
    items = run_async(get_registry().call("get_news", limit=limit, default=[]))
    added = 0
    skipped = 0
    for item in items:
        digest = _content_hash(item.title, item.source or "unknown")
        if db.query(News.id).filter(News.content_hash == digest).first():
            skipped += 1
            continue
        text = f"{item.title} {item.content or ''}"
        sentiment = item.sentiment if item.sentiment else score_text(text)
        importance = item.importance if item.importance else importance_score(text, item.title)
        industries = detect_industries(text)
        db.add(
            News(
                title=item.title,
                content=item.content,
                source=item.source or "未知来源",
                url=item.url,
                published_at=item.published_at or utcnow(),
                related_fund=item.related_fund,
                related_industry=item.related_industry or (industries[0] if industries else None),
                sentiment=round(float(sentiment), 4),
                importance=round(float(importance), 4),
                content_hash=digest,
                retrieved_at=utcnow(),
            )
        )
        added += 1
    db.commit()
    log.info("新闻同步完成: 新增 %d, 去重跳过 %d", added, skipped)
    return {"status": "synced", "new_rows": added, "duplicates_skipped": skipped}


def sync_policies(db, limit: int = 60) -> dict:
    items = run_async(get_registry().call("get_policies", limit=limit, default=[]))
    added = 0
    skipped = 0
    for item in items:
        digest = _content_hash(item.title, item.source or "unknown")
        if db.query(Policy.id).filter(Policy.content_hash == digest).first():
            skipped += 1
            continue
        text = f"{item.title} {item.content or ''}"
        sentiment = item.sentiment if item.sentiment else score_text(text)
        importance = item.importance if item.importance else importance_score(text, item.title)
        industries = detect_industries(text)
        db.add(
            Policy(
                title=item.title,
                content=item.content,
                source=item.source or "公开政策信息",
                url=item.url,
                published_at=item.published_at or utcnow(),
                department=item.department,
                policy_type=item.policy_type,
                related_industry=item.related_industry or (industries[0] if industries else None),
                sentiment=round(float(sentiment), 4),
                impact_score=round(float(item.impact_score), 4),
                importance=round(float(importance), 4),
                content_hash=digest,
                retrieved_at=utcnow(),
            )
        )
        added += 1
    db.commit()
    log.info("政策同步完成: 新增 %d, 去重跳过 %d", added, skipped)
    return {"status": "synced", "new_rows": added, "duplicates_skipped": skipped}


def _news_dict(row: News) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "source": row.source,
        "url": row.url,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "related_fund": row.related_fund,
        "related_industry": row.related_industry,
        "sentiment": row.sentiment,
        "sentiment_label": sentiment_label(row.sentiment),
        "importance": row.importance,
        "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
    }


def _policy_dict(row: Policy) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "source": row.source,
        "url": row.url,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "department": row.department,
        "policy_type": row.policy_type,
        "related_industry": row.related_industry,
        "sentiment": row.sentiment,
        "impact_score": row.impact_score,
        "importance": row.importance,
        "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
    }


def news_list(
    db,
    limit: int = 50,
    industry: str | None = None,
    related_fund: str | None = None,
    min_importance: float | None = None,
) -> list[dict]:
    q = db.query(News)
    if industry:
        q = q.filter(News.related_industry == industry)
    if related_fund:
        q = q.filter(News.related_fund == related_fund)
    if min_importance is not None:
        q = q.filter(News.importance >= min_importance)
    rows = q.order_by(News.published_at.desc()).limit(min(limit, 200)).all()
    return [_news_dict(r) for r in rows]


def policy_list(db, limit: int = 50, industry: str | None = None) -> list[dict]:
    q = db.query(Policy)
    if industry:
        q = q.filter(Policy.related_industry == industry)
    rows = q.order_by(Policy.published_at.desc()).limit(min(limit, 200)).all()
    return [_policy_dict(r) for r in rows]


def news_for_fund(db, fund: Fund, limit: int = 6) -> list[dict]:
    """基金相关新闻：直接关联 + 行业关联。"""
    industries = {row[0] for row in db.query(FundHolding.industry).filter(FundHolding.fund_id == fund.id).all()}
    q = db.query(News).filter(
        (News.related_fund == fund.fund_code)
        | (News.related_industry.in_(industries) if industries else News.related_industry.is_(None))
    )
    rows = q.order_by(News.published_at.desc()).limit(limit).all()
    return [_news_dict(r) for r in rows]


def policies_for_fund(db, fund: Fund, limit: int = 6) -> list[dict]:
    industries = {row[0] for row in db.query(FundHolding.industry).filter(FundHolding.fund_id == fund.id).all()}
    q = db.query(Policy).filter(
        Policy.related_industry.in_(industries) if industries else Policy.related_industry.is_(None)
    )
    rows = q.order_by(Policy.published_at.desc()).limit(limit).all()
    return [_policy_dict(r) for r in rows]


def aggregate_sentiment(db, industries: list[str] | None = None) -> dict:
    """新闻/政策情绪聚合（全市场 + 分行业）。"""
    news_rows = db.query(News.related_industry, News.sentiment).all()
    policy_rows = db.query(Policy.related_industry, Policy.sentiment).all()

    def _avg(rows, column_filter):
        subset = [s for _, s in rows]
        return round(sum(subset) / len(subset), 4) if subset else 0.0

    def _avg_by_industry(rows, industries_filter):
        result: dict[str, float] = {}
        for industry, sentiment in rows:
            if industry is None or (industries_filter and industry not in industries_filter):
                continue
            result.setdefault(industry, []).append(sentiment)
        return {k: round(sum(v) / len(v), 4) for k, v in result.items()}

    news_avg = _avg(news_rows, None)
    policy_avg = _avg(policy_rows, None)
    return {
        "news": {
            "avg_sentiment": news_avg,
            "count": len(news_rows),
            "industry_sentiment": _avg_by_industry(news_rows, industries),
        },
        "policies": {
            "avg_sentiment": policy_avg,
            "avg_impact": round(sum(s for _, s in policy_rows) / len(policy_rows), 4) if policy_rows else 0.0,
            "count": len(policy_rows),
            "industry_sentiment": _avg_by_industry(policy_rows, industries),
        },
    }

"""日期与时间工具。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    from app.core.config import get_settings

    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(get_settings().TZ))
    except Exception:
        return datetime.now()


def today() -> date:
    return date.today()


def parse_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def to_iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def last_trading_day(day: date | None = None) -> date:
    """最近一个交易日（简单地跳过周末；节假日按数据实际日期为准）。"""
    day = day or today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def days_ago(n: int) -> date:
    return today() - timedelta(days=n)

"""轻量数据库迁移：create_all 之后为已有表补齐缺失列。

开发期使用 SQLite / 已有生产库演进时，create_all 不会 ALTER 已存在表；
本模块按 ORM 模型检查实际列并 ADD COLUMN 缺失项（仅新增列，不改不删）。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

log = logging.getLogger("app.db")


def ensure_columns(engine, table_name: str, expected: dict[str, str], default_null: bool = True) -> None:
    """expected: {列名: 类型}；缺列则 ADD COLUMN（可空，不迁移数据）。"""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for col_name, col_type in expected.items():
            if col_name in existing:
                continue
            conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN "{col_name}" {col_type}'))
            log.info("迁移: %s 新增列 %s", table_name, col_name)


def run_migrations() -> None:
    from app.db.session import engine

    ensure_columns(
        engine,
        "news",
        {
            "quality": "VARCHAR(16)",
            "as_of": "DATE",
        },
    )
    ensure_columns(
        engine,
        "policies",
        {
            "quality": "VARCHAR(16)",
            "as_of": "DATE",
        },
    )
    ensure_columns(
        engine,
        "macro_data",
        {
            "quality": "VARCHAR(16)",
            "as_of": "DATE",
        },
    )
    ensure_columns(
        engine,
        "fund_holdings",
        {
            "available_at": "DATE",
        },
    )
    ensure_columns(
        engine,
        "messages",
        {
            "context_hash": "VARCHAR(16)",
        },
    )

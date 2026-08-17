"""应用配置。所有敏感配置来自环境变量 / .env，绝不写死在源码中。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "基金智能分析预测平台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库 / 缓存
    DATABASE_URL: str = "sqlite:///./fund.db"
    REDIS_URL: str = ""

    # 安全
    SECRET_KEY: str = "dev-secret-change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # LLM（DeepSeek，OpenAI 兼容接口）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_TIMEOUT: float = 60.0
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.7

    # 数据源
    DATA_PROVIDER_ORDER: str = "eastmoney,mock"
    PROVIDER_TIMEOUT: float = 12.0
    PROVIDER_MAX_RETRIES: int = 2
    PROVIDER_MIN_INTERVAL: float = 0.35  # 同源请求最小间隔（秒），用于限流
    CACHE_TTL_SECONDS: int = 300
    ANALYSIS_CACHE_TTL: int = 600
    CONTEXT_CACHE_TTL: int = 600

    # 同步调度
    QUOTE_SYNC_MINUTES: int = 5
    DAILY_SYNC_TIME: str = "08:00"
    ENABLE_AUTO_SYNC: bool = True

    # 演示数据 / 演示账号
    SEED_DEMO_DATA: bool = True
    DEMO_USERNAME: str = "demo"
    DEMO_PASSWORD: str = "demo123456"
    DEMO_EMAIL: str = "demo@example.com"

    # 邮件（SMTP）
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_SSL: bool = True

    # 存储与日志
    STORAGE_DIR: str = "storage"
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"

    # 时区
    TZ: str = "Asia/Shanghai"

    # 预测引擎
    MODEL_MIN_SAMPLES: int = 300
    MODEL_RETRAIN_DAYS: int = 7
    RF_MIN_SAMPLES: int = 800
    MODEL_JOBS: int = 1  # 沙箱/受限环境用 1（joblib 多线程需要命名管道）；生产可设 -1 或核数
    DATASET_YEARS: float = 4.0  # 训练集回溯年数
    CV_N_SPLITS: int = 4  # Purged Walk-Forward 折数
    CALIBRATION_METHOD: str = "isotonic"  # isotonic | sigmoid（样本不足自动 uncalibrated）
    BACKTEST_MODEL: str = "random_forest"  # 回测默认模型
    BACKTEST_RETRAIN_EVERY: int = 60
    LEDGER_ENABLED: bool = True  # 预测台账持久化
    AUTO_WARMUP_TRAIN: bool = True  # 启动后台预热训练（不阻塞启动）

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def provider_order(self) -> list[str]:
        return [p.strip() for p in self.DATA_PROVIDER_ORDER.split(",") if p.strip()]

    @property
    def storage_dir(self) -> Path:
        return BASE_DIR / self.STORAGE_DIR

    @property
    def models_dir(self) -> Path:
        return self.storage_dir / "models"

    @property
    def log_dir(self) -> Path:
        return BASE_DIR / self.LOG_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()

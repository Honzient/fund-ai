"""模型包：导入全部 ORM 模型以便 create_all 注册。"""
from app.models.fund import Fund, FundDailyData, FundHolding
from app.models.llm import AnalysisSnapshot, Conversation, Message
from app.models.macro import MacroData
from app.models.market import MarketIndex, MarketIndexData
from app.models.news import News, Policy
from app.models.task import Report, ScheduledAnalysis, TaskRun
from app.models.user import AssetType, Notification, User, UserSetting, Watchlist

__all__ = [
    "Fund",
    "FundDailyData",
    "FundHolding",
    "MarketIndex",
    "MarketIndexData",
    "MacroData",
    "News",
    "Policy",
    "User",
    "Watchlist",
    "UserSetting",
    "Notification",
    "AssetType",
    "TaskRun",
    "ScheduledAnalysis",
    "Report",
    "Conversation",
    "Message",
    "AnalysisSnapshot",
]

"""Schema 包。"""
from app.schemas.analysis import AnalysisRequest
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.schemas.chat import ChatRequest, ConversationCreate
from app.schemas.fund import WatchlistCreate, WatchlistUpdate
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.schemas.settings import KeySetRequest, SettingsUpdate

__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "UserOut",
    "TokenOut",
    "WatchlistCreate",
    "WatchlistUpdate",
    "ChatRequest",
    "ConversationCreate",
    "ScheduleCreate",
    "ScheduleUpdate",
    "AnalysisRequest",
    "SettingsUpdate",
    "KeySetRequest",
]

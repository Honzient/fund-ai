"""通知渠道统一接口。后续可扩展 Telegram / Discord / 企业微信 / 钉钉 / 飞书 / Push。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def send(self, user_id: int, title: str, content: str, type: str = "report") -> bool: ...

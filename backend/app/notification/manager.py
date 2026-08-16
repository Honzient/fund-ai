"""通知管理器：站内通知始终记录，Email 按渠道与用户设置发送。"""
from __future__ import annotations

from app.core.logging import get_logger
from app.notification.email_provider import EmailProvider
from app.notification.in_app import InAppProvider

log = get_logger("app.notification")


class NotificationManager:
    def __init__(self) -> None:
        self._providers = {
            "in_app": InAppProvider(),
            "email": EmailProvider(),
            # 未来扩展: "telegram": ..., "discord": ..., "wecom": ..., "dingtalk": ..., "feishu": ...
        }

    def provider_names(self) -> list[str]:
        return list(self._providers.keys())

    def notify(
        self,
        user_id: int,
        title: str,
        content: str,
        type: str = "report",
        channels: list[str] | None = None,
    ) -> dict:
        """发送通知。站内通知始终发送；其他渠道按请求与可用性。"""
        channels = channels or ["in_app"]
        results: dict[str, bool] = {}
        for channel in channels:
            provider = self._providers.get(channel)
            if provider is None:
                results[channel] = False
                continue
            try:
                results[channel] = provider.send(user_id, title, content, type)
            except Exception as exc:  # noqa: BLE001
                log.warning("通知渠道 %s 失败: %s", channel, exc)
                results[channel] = False
        return results


_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    global _manager
    if _manager is None:
        _manager = NotificationManager()
    return _manager

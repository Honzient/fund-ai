"""Email 通知 Provider（SMTP）。"""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import User, UserSetting

log = get_logger("app.notification")


class EmailProvider:
    name = "email"

    def available(self) -> bool:
        settings = get_settings()
        return bool(settings.SMTP_HOST and settings.SMTP_FROM)

    def _recipient(self, user_id: int) -> str | None:
        db = SessionLocal()
        try:
            row = (
                db.query(UserSetting)
                .filter(UserSetting.user_id == user_id, UserSetting.key == "email_to")
                .first()
            )
            if row and row.value:
                return row.value
            user = db.get(User, user_id)
            return user.email if user and user.email else None
        finally:
            db.close()

    def send(self, user_id: int, title: str, content: str, type: str = "report") -> bool:
        recipient = self._recipient(user_id)
        if not recipient or not self.available():
            return False
        settings = get_settings()
        try:
            asyncio.run(self._send_async(settings, recipient, title, content))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("邮件发送失败: %s", exc)
            return False

    async def _send_async(self, settings, recipient: str, title: str, content: str) -> None:
        import aiosmtplib
        from email.mime.text import MIMEText

        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = settings.SMTP_FROM
        msg["To"] = recipient
        kwargs = {
            "hostname": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "username": settings.SMTP_USER or None,
            "password": settings.SMTP_PASSWORD or None,
            "use_tls": settings.SMTP_SSL,
            "timeout": 15,
        }
        await aiosmtplib.send(msg, **kwargs)

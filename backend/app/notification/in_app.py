"""站内通知 Provider。"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.models import Notification


class InAppProvider:
    name = "in_app"

    def available(self) -> bool:
        return True

    def send(self, user_id: int, title: str, content: str, type: str = "report") -> bool:
        db = SessionLocal()
        try:
            db.add(
                Notification(user_id=user_id, title=title, content=content, type=type, read=False)
            )
            db.commit()
            return True
        except Exception:  # noqa: BLE001
            db.rollback()
            return False
        finally:
            db.close()

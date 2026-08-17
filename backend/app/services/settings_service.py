"""用户设置服务（API Key 加密存储）。"""
from __future__ import annotations

import json

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import UserSetting
from app.utils.dates import utcnow

LLM_SETTINGS_KEY = "llm_settings"
NOTIFY_SETTINGS_KEY = "notification_settings"
SYNC_SETTINGS_KEY = "sync_settings"
API_KEY_KEY = "deepseek_api_key"
EMAIL_TO_KEY = "email_to"


def _get(db, user_id: int, key: str) -> UserSetting | None:
    return (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == key)
        .first()
    )


def _set_value(db, user_id: int, key: str, value: str | None) -> None:
    row = _get(db, user_id, key)
    if row is None:
        row = UserSetting(user_id=user_id, key=key)
        db.add(row)
    row.value = value
    row.updated_at = utcnow()


def _get_json(db, user_id: int, key: str, default: dict) -> dict:
    row = _get(db, user_id, key)
    if row is None or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:  # noqa: BLE001
        return default


def get_settings_payload(db, user_id: int) -> dict:
    settings = get_settings()
    llm = _get_json(db, user_id, LLM_SETTINGS_KEY, {})
    notify = _get_json(
        db, user_id, NOTIFY_SETTINGS_KEY, {"email_enabled": False, "email_to": None, "channels": ["in_app"]}
    )
    sync = _get_json(db, user_id, SYNC_SETTINGS_KEY, {"quote_interval_minutes": settings.QUOTE_SYNC_MINUTES})
    key_row = _get(db, user_id, API_KEY_KEY)
    return {
        "llm": {
            "provider": llm.get("provider", "deepseek"),
            "model": llm.get("model") or settings.DEEPSEEK_MODEL,
            "base_url": llm.get("base_url") or settings.DEEPSEEK_BASE_URL,
            "has_api_key_env": bool(settings.DEEPSEEK_API_KEY),
            "has_user_key": bool(key_row and key_row.secret),
        },
        "notifications": notify,
        "sync": sync,
        "timezone": settings.TZ,
    }


def update_settings(db, user_id: int, payload: dict) -> dict:
    llm = payload.get("llm")
    if llm is not None:
        current = _get_json(db, user_id, LLM_SETTINGS_KEY, {})
        for field in ("provider", "model", "base_url"):
            if llm.get(field) is not None:
                current[field] = llm[field]
        _set_value(db, user_id, LLM_SETTINGS_KEY, json.dumps(current, ensure_ascii=False))
    notify = payload.get("notifications")
    if notify is not None:
        current = _get_json(
            db, user_id, NOTIFY_SETTINGS_KEY,
            {"email_enabled": False, "email_to": None, "channels": ["in_app"]},
        )
        current["email_enabled"] = bool(notify.get("email_enabled", current["email_enabled"]))
        current["channels"] = notify.get("channels") or current["channels"]
        email_to = notify.get("email_to")
        if email_to is not None:
            current["email_to"] = str(email_to)
            _set_value(db, user_id, EMAIL_TO_KEY, str(email_to))
        _set_value(db, user_id, NOTIFY_SETTINGS_KEY, json.dumps(current, ensure_ascii=False))
    sync = payload.get("sync")
    if sync is not None:
        current = _get_json(db, user_id, SYNC_SETTINGS_KEY, {})
        if sync.get("quote_interval_minutes") is not None:
            current["quote_interval_minutes"] = int(sync["quote_interval_minutes"])
        _set_value(db, user_id, SYNC_SETTINGS_KEY, json.dumps(current))
    db.commit()
    return get_settings_payload(db, user_id)


def set_api_key(db, user_id: int, api_key: str) -> dict:
    row = _get(db, user_id, API_KEY_KEY)
    if row is None:
        row = UserSetting(user_id=user_id, key=API_KEY_KEY)
        db.add(row)
    row.secret = encrypt_secret(api_key)
    row.value = None
    row.updated_at = utcnow()
    db.commit()
    # Key 轮换：立即失效旧 Provider 缓存，禁止继续使用旧 Key
    from app.llm import get_llm_manager

    get_llm_manager().invalidate_provider(user_id)
    return {"status": "saved", "has_user_key": True}


def delete_api_key(db, user_id: int) -> dict:
    row = _get(db, user_id, API_KEY_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    from app.llm import get_llm_manager

    get_llm_manager().invalidate_provider(user_id)
    return {"status": "deleted", "has_user_key": False}

"""安全工具：密码哈希、JWT、敏感配置加密、日志脱敏。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet

from app.core.config import get_settings

# ---------- 密码哈希（PBKDF2-SHA256，无额外依赖） ----------

_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


# ---------- JWT ----------


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        return None


# ---------- 敏感配置加密（Fernet，密钥由 SECRET_KEY 派生） ----------


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        return _fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


# ---------- 日志脱敏 ----------

_SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key[\"'\s:=]+)([A-Za-z0-9_\-]{6,})"),
    re.compile(r"(?i)(password[\"'\s:=]+)([^\s,;]+)"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+"),
]


def redact(text: str) -> str:
    out = text
    for pattern in _SENSITIVE_PATTERNS:
        out = pattern.sub(lambda m: (m.group(1) + "****" if m.lastindex else m.group(0)[:8] + "****"), out)
    return out

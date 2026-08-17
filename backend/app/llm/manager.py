"""LLM 管理器：环境变量 Key 优先，用户自定义 Key（加密存储）可覆盖。"""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.db.session import SessionLocal
from app.llm.base import LLMProvider, LLMUnavailableError
from app.llm.deepseek import DeepSeekProvider
from app.models import UserSetting

log = get_logger("app.llm")

PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "deepseek": DeepSeekProvider,
    # 未来扩展: "openai": OpenAIProvider, "claude": ClaudeProvider, "qwen": QwenProvider
}


def _user_api_key(user_id: int | None) -> str:
    if user_id is None:
        return ""
    db = SessionLocal()
    try:
        row = (
            db.query(UserSetting)
            .filter(UserSetting.user_id == user_id, UserSetting.key == "deepseek_api_key")
            .first()
        )
        if row and row.secret:
            return decrypt_secret(row.secret)
        return ""
    finally:
        db.close()


class LLMManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._providers: dict[str, LLMProvider] = {}

    @staticmethod
    def _credential_fingerprint(api_key: str) -> str:
        """凭证指纹：API Key 变更后缓存 key 必然改变（旧 Provider 自动失效）。"""
        import hashlib

        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12] if api_key else "none"

    def _get_provider(self, provider: str, user_id: int | None = None) -> LLMProvider:
        provider = provider or "deepseek"
        api_key = ""
        if provider == "deepseek":
            api_key = _user_api_key(user_id) or self.settings.DEEPSEEK_API_KEY
        # 缓存 key 绑定凭证指纹 + 基础配置：Key 轮换/配置变更后旧缓存自动失效
        key = f"{provider}:{user_id or 0}:{self._credential_fingerprint(api_key)}"
        if key not in self._providers:
            cls = PROVIDER_CLASSES.get(provider)
            if cls is None:
                raise LLMUnavailableError(f"未知 LLM Provider: {provider}")
            if provider == "deepseek":
                self._providers[key] = DeepSeekProvider(
                    api_key=api_key,
                    base_url=self.settings.DEEPSEEK_BASE_URL,
                    model=self.settings.DEEPSEEK_MODEL,
                )
            else:
                self._providers[key] = cls()
        return self._providers[key]

    def invalidate_provider(self, user_id: int | None = None) -> int:
        """使指定用户（或全部）的 Provider 缓存失效。返回失效数量。"""
        prefix = f"deepseek:{user_id or 0}:"
        stale = [k for k in self._providers if k.startswith(prefix)]
        for k in stale:
            self._providers.pop(k, None)
        if user_id is None:
            stale += [k for k in self._providers if k.startswith("deepseek:")]
            for k in stale:
                self._providers.pop(k, None)
        return len(stale)

    def available(self, user_id: int | None = None) -> bool:
        try:
            return self._get_provider("deepseek", user_id).available()
        except Exception:  # noqa: BLE001
            return False

    def status(self, user_id: int | None = None) -> dict:
        has_env = bool(self.settings.DEEPSEEK_API_KEY)
        has_user = bool(_user_api_key(user_id))
        return {
            "provider": "deepseek",
            "model": self.settings.DEEPSEEK_MODEL,
            "base_url": self.settings.DEEPSEEK_BASE_URL,
            "available": self.available(user_id),
            "has_api_key_env": has_env,
            "has_user_key": has_user,
        }

    async def complete(
        self,
        messages: list[dict],
        user_id: int | None = None,
        provider: str = "deepseek",
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        llm = self._get_provider(provider, user_id)
        try:
            return await asyncio.wait_for(
                llm.chat(
                    messages,
                    temperature=temperature if temperature is not None else self.settings.LLM_TEMPERATURE,
                    max_tokens=max_tokens or self.settings.LLM_MAX_TOKENS,
                    timeout=timeout or self.settings.LLM_TIMEOUT,
                ),
                timeout=(timeout or self.settings.LLM_TIMEOUT) + 10,
            )
        except asyncio.TimeoutError as exc:
            raise LLMUnavailableError("LLM 调用超时") from exc


_manager: LLMManager | None = None


def get_llm_manager() -> LLMManager:
    global _manager
    if _manager is None:
        _manager = LLMManager()
    return _manager

"""DeepSeek Provider（OpenAI 兼容 chat/completions 接口）。"""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import LLMProvider, LLMUnavailableError

log = get_logger("app.llm")


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        settings = get_settings()
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = (base_url or settings.DEEPSEEK_BASE_URL).rstrip("/")
        self.model = model or settings.DEEPSEEK_MODEL

    def available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> str:
        if not self.available():
            raise LLMUnavailableError("DeepSeek API Key 未配置")
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            log.warning("DeepSeek 接口返回错误: %s %s", exc.response.status_code, exc.response.text[:200])
            raise LLMUnavailableError(f"DeepSeek 接口错误 {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            log.warning("DeepSeek 网络错误: %s", exc)
            raise LLMUnavailableError(f"DeepSeek 网络错误: {exc}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise LLMUnavailableError("DeepSeek 返回为空")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if not content:
            raise LLMUnavailableError("DeepSeek 返回内容为空")
        return content.strip()
